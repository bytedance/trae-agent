import argparse
import csv
import json
import os

from rich.console import Console
from rich.table import Table


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output_path", type=str, required=True)
    parser.add_argument("--group_id", type=int, required=False, default=None)
    args = parser.parse_args()

    output_path = args.output_path
    statistics_path = output_path + "/statistics"

    if args.group_id is not None:
        statistics_folder_path = statistics_path + f"/group_{args.group_id}"
        result = {f"group_{args.group_id}": analyze_group(statistics_folder_path)}
    else:
        # get all groups in the statistics directory
        group_ids = [
            f
            for f in os.listdir(statistics_path)
            if os.path.isdir(os.path.join(statistics_path, f))
        ]
        result = {}
        for group_id in group_ids:
            statistics_folder_path = statistics_path + f"/{group_id}"
            result[f"{group_id}"] = analyze_group(statistics_folder_path)

    # sort result by success_rate_among_all
    result = dict(
        sorted(result.items(), key=lambda item: item[1]["success_rate_among_all"], reverse=True)
    )

    table = Table(title=f"Statistics for Selector Experiment {output_path}")
    # save to csv
    with open(output_path + "/analysis.csv", "w") as f:
        writer = csv.writer(f)
        table_header = [
            "group_id",
            "total",
            "completion_rate",
            "all_success",
            "all_failed",
            "need_to_select",
            "success_selection",
            "success_selection_in_need_to_select",
            "success_rate_in_need_to_select",
            "success_rate_among_all",
        ]
        for header in table_header:
            if header == "success_rate_in_need_to_select":
                table.add_column(header, justify="right", no_wrap=True, style="cyan")
            elif header == "success_rate_among_all":
                table.add_column(header, justify="right", no_wrap=True, style="magenta")
            else:
                table.add_column(header, justify="right", no_wrap=True)
        writer.writerow(table_header)

        max_success_rate_in_need_to_select = 0
        max_success_rate_group_id = ""
        max_success_rate_among_all = 0
        max_success_rate_among_all_group_id = ""
        table_rows = []
        for group_id, record in result.items():
            row = [
                group_id,
                record["total"],
                record["completion_rate"],
                record["all_success"],
                record["all_failed"],
                record["need_to_select"],
                record["success_selection"],
                record["success_selection_in_need_to_select"],
                record["success_rate_in_need_to_select"],
                record["success_rate_among_all"],
            ]

            # make the largest success rate in need to select and success rate among all bold
            if float(record["success_rate_in_need_to_select"]) > max_success_rate_in_need_to_select:
                max_success_rate_in_need_to_select = float(record["success_rate_in_need_to_select"])
                max_success_rate_group_id = group_id
            if float(record["success_rate_among_all"]) > max_success_rate_among_all:
                max_success_rate_among_all = float(record["success_rate_among_all"])
                max_success_rate_among_all_group_id = group_id
            table_rows.append(row)
            writer.writerow(row)

        for row in table_rows:
            if row[0] == max_success_rate_group_id:
                row[8] = f"[strong][underline]{row[8] * 100:.2f}%[/underline][/strong]"
            if row[0] == max_success_rate_among_all_group_id:
                row[9] = f"[strong][underline]{row[9] * 100:.2f}%[/underline][/strong]"
            for i in range(len(row)):
                if isinstance(row[i], float):
                    row[i] = f"{row[i] * 100:.2f}%"
                else:
                    row[i] = str(row[i])
            table.add_row(*row)

    # print in table
    console = Console()
    console.print(table)


def analyze_group(statistics_folder_path, total_num_instances=500):
    all_success = 0
    all_failed = 0
    need_to_select = 0
    success_selection = 0
    success_selection_in_need_to_select = 0
    total = 0

    # list all json files in the statistics folder
    json_files = [f for f in os.listdir(statistics_folder_path) if f.endswith(".json")]
    for json_file in json_files:
        with open(os.path.join(statistics_folder_path, json_file), "r") as f:
            try:
                data = json.loads(f.read())
            except Exception:
                print(f"Error loading {os.path.join(statistics_folder_path, json_file)}")
            if data["is_all_success"]:
                all_success += 1
            if data["is_all_failed"]:
                all_failed += 1
            if not data["is_all_success"] and not data["is_all_failed"]:
                need_to_select += 1
                if data["is_success"] == 1:
                    success_selection_in_need_to_select += 1
            if data["is_success"] == 1:
                success_selection += 1
            total += 1

    return {
        "total": total,
        "completion_rate": float(total) / float(total_num_instances),
        "all_success": all_success,
        "all_failed": all_failed,
        "need_to_select": need_to_select,
        "success_selection": success_selection,
        "success_selection_in_need_to_select": success_selection_in_need_to_select,
        "success_rate_in_need_to_select": float(success_selection_in_need_to_select)
        / float(need_to_select)
        if need_to_select > 0
        else 0,
        "success_rate_among_all": float(success_selection) / float(total) if total > 0 else 0,
    }


if __name__ == "__main__":
    main()
