import io
import json
import os
import re
import tokenize
from pathlib import Path

from unidiff import PatchSet


def remove_comments_from_line(line: str) -> str:
    try:
        tokens = tokenize.generate_tokens(io.StringIO(line).readline)
        result_parts = []
        prev_end = (0, 0)

        for tok_type, tok_str, tok_start, tok_end, _ in tokens:
            if tok_type == tokenize.COMMENT:
                break
            (srow, scol) = tok_start
            if srow == 1 and scol > prev_end[1]:
                result_parts.append(line[prev_end[1] : scol])
            result_parts.append(tok_str)
            prev_end = tok_end

        return "".join(result_parts).rstrip()
    except tokenize.TokenError:
        if "#" in line:
            return line.split("#", 1)[0].rstrip()
        return line


def clean_patch(ori_patch_text):
    # in case ori_patch_text has unexpected trailing newline characters
    # processed_ori_patch_text = ""
    # previous_line = None
    # for line in ori_patch_text.split('\n'):
    #     if previous_line is None:
    #         previous_line = line
    #         continue
    #     elif previous_line.strip() == '' and "diff --git" in line:
    #         previous_line = line
    #         continue
    #     else:
    #         processed_ori_patch_text = processed_ori_patch_text + previous_line + "\n"
    #     previous_line = line
    # if previous_line:
    #     processed_ori_patch_text = processed_ori_patch_text + previous_line

    processed_ori_patch_text = ori_patch_text
    patch = PatchSet(processed_ori_patch_text)
    extracted_lines = []
    delete_lines = []
    add_lines = []
    for patched_file in patch:
        for hunk in patched_file:
            for line in hunk:
                if line.is_added:
                    content = line.value.lstrip("+")
                    if content.strip() and not re.match(r"^\s*#", content):
                        content = remove_comments_from_line(content.rstrip())
                        extracted_lines.append("+" + content)
                        add_lines.append(content)
                elif line.is_removed:
                    content = line.value.lstrip("-")
                    if content.strip() and not re.match(r"^\s*#", content):
                        content = remove_comments_from_line(content.rstrip())
                        extracted_lines.append("-" + content)
                        delete_lines.append(content)
    new_patch_text = "\n".join(extracted_lines)

    new_patch_text = re.sub(r"\s+", "", new_patch_text)

    return new_patch_text


def save_patches(instance_id, patches_path, patches, group_id=1):
    trial_index = 1

    dir_path = Path(patches_path) / f"group_{group_id}"
    dir_path.mkdir(parents=True, exist_ok=True)

    def get_unique_filename(patches_path, trial_index):
        filename = f"{instance_id}_{trial_index}.patch"
        while os.path.exists(dir_path / filename):
            trial_index += 1
            filename = f"{instance_id}_{trial_index}.patch"
        return filename

    patch_file = get_unique_filename(patches_path, trial_index)

    clean_patch = patches
    with open(dir_path / patch_file, "w") as file:
        file.write(clean_patch)

    print(f"Patches saved in {dir_path / patch_file}")


def get_trajectory_filename(instance_id, traj_dir, group_id=1, voting_id=1):
    dir_path = Path(traj_dir) / f"group_{group_id}"
    dir_path.mkdir(parents=True, exist_ok=True)
    print("dir_path", dir_path)

    def get_unique_filename():
        trial_index = 1
        filename = f"{instance_id}_voting_{voting_id}_trail_{trial_index}.json"
        while os.path.exists(dir_path / filename):
            trial_index += 1
            filename = f"{instance_id}_voting_{voting_id}_trail_{trial_index}.json"
        return filename

    filename = dir_path / get_unique_filename()
    return filename.absolute().as_posix()


def save_selection_success(
    instance_id: str,
    statistics_path: str,
    patch_id: int,
    is_success: int,
    group_id=1,
    is_all_success=False,
    is_all_failed=False,
):
    dir_path = Path(statistics_path) / f"group_{group_id}"
    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / f"{instance_id}.json"

    with open(file_path, "w") as statistics_file:
        statistics_file.write(
            json.dumps(
                {
                    "instance_id": instance_id,
                    "patch_id": patch_id,
                    "is_success": is_success,
                    "is_all_success": is_all_success,
                    "is_all_failed": is_all_failed,
                },
                indent=4,
                sort_keys=True,
                ensure_ascii=False,
            )
        )
