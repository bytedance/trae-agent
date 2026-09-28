# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""The issue forms must ask for labels this repository actually defines.

GitHub attaches only the declared names that exist as labels, so a form that names a label
the repository has never had files its issue with no marker at all. `bug-report.yml` did
exactly that: it asked for `status/need_triage`, while the label, the other three forms and
the maintainers' queue all use `status/need-triage`. Every bug report therefore arrived
without the triage flag -- see the counts recorded in the linked issue.

These cases read the template files themselves, so they need no network access and no
credentials; they fail on the shape of the configuration, which is where the drift happens.
"""

import re
import unittest
from pathlib import Path

import yaml

# `.github/ISSUE_TEMPLATE/config.yml` is the sidebar of contact links, not a form.
NON_FORM_FILES = frozenset({"config.yml"})

# Label names in this repository are `<namespace>/<kebab-case>`; none uses an underscore.
LABEL_NAME = re.compile(r"^[a-z0-9]+(?:[-/][a-z0-9]+)*$")


def template_files(root: Path) -> list[Path]:
    """Every issue form under `root`, in a stable order."""
    return sorted(
        path
        for path in (root / ".github" / "ISSUE_TEMPLATE").glob("*.yml")
        if path.name not in NON_FORM_FILES
    )


def labels_of(path: Path) -> list[str]:
    """The `labels:` list declared by one issue form."""
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise AssertionError(f"{path.name} is not a YAML mapping")
    labels = document.get("labels")
    if not isinstance(labels, list) or not all(isinstance(label, str) for label in labels):
        raise AssertionError(f"{path.name} declares no list of label names, got {labels!r}")
    return labels


def namespace(labels: list[str], prefix: str) -> list[str]:
    """The labels of one namespace, e.g. `status`, from a declared list."""
    return [label for label in labels if label.startswith(f"{prefix}/")]


class IssueTemplateLabelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        here = Path(__file__).resolve()
        for parent in here.parents:
            if (parent / ".github" / "ISSUE_TEMPLATE").is_dir():
                cls._root = parent
                break
        else:  # pragma: no cover - a source distribution without `.github`
            raise unittest.SkipTest(f"no .github/ISSUE_TEMPLATE above {here}")
        cls._files = template_files(cls._root)
        if not cls._files:  # pragma: no cover
            raise unittest.SkipTest(f"no issue forms found under {cls._root}")
        cls._labels: dict[str, list[str]] = {path.name: labels_of(path) for path in cls._files}

    def test_the_forms_are_found(self):
        names = {path.name for path in self._files}
        self.assertIn("bug-report.yml", names)
        self.assertGreaterEqual(len(names), 3, names)

    def test_every_label_is_kebab_cased(self):
        for filename, labels in self._labels.items():
            for label in labels:
                with self.subTest(file=filename, label=label):
                    self.assertRegex(label, LABEL_NAME)

    def test_every_form_declares_one_type_and_one_status_label(self):
        for filename, labels in self._labels.items():
            with self.subTest(file=filename):
                self.assertEqual(len(namespace(labels, "type")), 1, labels)
                self.assertEqual(len(namespace(labels, "status")), 1, labels)

    def test_all_forms_share_the_same_status_label(self):
        statuses = {namespace(labels, "status")[0] for labels in self._labels.values()}
        self.assertEqual(
            len(statuses), 1, f"the forms disagree about the triage label: {self._labels}"
        )

    def test_bug_report_asks_for_the_triage_label_the_other_forms_use(self):
        others = {
            namespace(labels, "status")[0]
            for filename, labels in self._labels.items()
            if filename != "bug-report.yml"
        }
        self.assertEqual(len(others), 1, others)
        self.assertEqual(namespace(self._labels["bug-report.yml"], "status"), [next(iter(others))])


if __name__ == "__main__":
    unittest.main()
