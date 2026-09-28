"""Keep docs/legacy_config.md followable against trae_config.json.example.

The guide is the only page that tells a reader which values in the example JSON to replace. On main it
names four of the eight placeholders the file contains, so a reader who works down the list saves a file
with four placeholders still in it. These cases hold the guide, the example file and the README together
in both directions.
"""

import json
import re
import unittest
from pathlib import Path

GUIDE_PATH = Path("docs") / "legacy_config.md"
EXAMPLE_PATH = Path("trae_config.json.example")
README_PATH = Path("README.md")
GITIGNORE_PATH = Path(".gitignore")

# '- Replace `"some_literal"` with ...' -- the only form the guide's setup step uses.
REPLACE_BULLET = re.compile(r'^\s*- Replace `"([^"]+)"', re.MULTILINE)
# A README link with an anchor, as written from docs/: [text](../README.md#anchor).
README_ANCHOR = re.compile(r"\]\(\.\./README\.md#([^)\s]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*$", re.MULTILINE)
FENCE_OPEN = re.compile(r"^```")
# The guide's promise that the credentials file cannot be committed by accident.
GITIGNORE_CLAIM = re.compile(r"`trae_config\.json`[^.]*\bignored by git")


def _slug(heading: str) -> str:
    """GitHub's anchor for a heading, restricted to headings the page can link with plain characters."""
    return re.sub(r"\s", "-", re.sub(r"[^a-z0-9 -]", "", heading.lower()))


def _string_values(node: object) -> list[str]:
    if isinstance(node, dict):
        found: list[str] = []
        for value in node.values():
            found.extend(_string_values(value))
        return found
    if isinstance(node, list):
        items: list[str] = []
        for value in node:
            items.extend(_string_values(value))
        return items
    if isinstance(node, str):
        return [node]
    return []


def _readme_anchors(readme: str) -> set[str]:
    """Anchors a page in docs/ can link to: slugs of README headings made of plain characters.

    Headings carrying an emoji are left out on purpose: GitHub keeps the emoji's variation selector in the
    slug it builds, so the README's gear-prefixed Configuration heading is anchored as "-configuration"
    and a page linking "#configuration" gets a dead link. Link the ASCII subheading below it instead.
    """
    headings: list[str] = []
    inside_fence = False
    for line in readme.splitlines():
        if FENCE_OPEN.match(line.strip()):
            inside_fence = not inside_fence
            continue
        if inside_fence:
            continue
        match = HEADING.match(line)
        if match is not None and match.group(1).isascii():
            headings.append(match.group(1))
    return {_slug(heading) for heading in headings}


class LegacyConfigGuideTest(unittest.TestCase):
    guide: str
    example_values: list[str]
    readme: str
    gitignore: str

    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parent
        while not (root / GUIDE_PATH).is_file():
            if root.parent == root:
                raise AssertionError(f"{GUIDE_PATH} not found above {Path(__file__).resolve()}")
            root = root.parent
        cls.guide = (root / GUIDE_PATH).read_text(encoding="utf-8")
        example = json.loads((root / EXAMPLE_PATH).read_text(encoding="utf-8"))
        cls.example_values = _string_values(example)
        cls.readme = (root / README_PATH).read_text(encoding="utf-8")
        cls.gitignore = (root / GITIGNORE_PATH).read_text(encoding="utf-8")

    def test_guide_names_every_placeholder_the_example_contains(self) -> None:
        """A reader working down the list must reach every placeholder in the file."""
        named = set(REPLACE_BULLET.findall(self.guide))
        placeholders = sorted(
            {value for value in self.example_values if value.startswith("your_")} - named
        )
        self.assertEqual(
            placeholders,
            [],
            "trae_config.json.example holds these placeholders that docs/legacy_config.md never names,"
            " so a reader following the guide leaves them in the file they hand to a model provider:"
            f" {placeholders}",
        )

    def test_every_literal_the_guide_names_exists_in_the_example(self) -> None:
        """The list must not send a reader looking for a value the file does not hold."""
        named = sorted(set(REPLACE_BULLET.findall(self.guide)))
        missing = [literal for literal in named if literal not in self.example_values]
        self.assertEqual(
            missing,
            [],
            "docs/legacy_config.md tells the reader to replace values that trae_config.json.example does"
            f" not contain: {missing}",
        )

    def test_every_placeholder_uses_the_your_prefix(self) -> None:
        """`you_azure_api_key` reads as already filled in, and a `your_` search walks past it."""
        misspelled = sorted(
            {
                value
                for value in self.example_values
                if value.startswith("you") and not value.startswith("your_")
            }
        )
        self.assertEqual(
            misspelled,
            [],
            "these placeholder values in trae_config.json.example begin with `you` but are not spelled"
            " `your_`, unlike every other credential placeholder in the repository:"
            f" {misspelled}",
        )

    def test_readme_links_point_at_headings_a_reader_can_reach(self) -> None:
        """Both links out of the page are its call to action; a dead anchor lands on the title."""
        anchors = sorted(set(README_ANCHOR.findall(self.guide)))
        self.assertTrue(anchors, "docs/legacy_config.md no longer links to README.md at all")
        unreachable = [anchor for anchor in anchors if anchor not in _readme_anchors(self.readme)]
        self.assertEqual(
            unreachable,
            [],
            "docs/legacy_config.md links to README.md anchors that no plain-character heading of"
            f" README.md produces, so the reader lands at the top of the page: {unreachable}",
        )

    def test_gitignore_promise_the_guide_makes_is_kept(self) -> None:
        """The guide tells the reader their key cannot be committed by accident."""
        self.assertRegex(
            self.guide,
            GITIGNORE_CLAIM,
            "docs/legacy_config.md no longer tells the reader the credentials file is git-ignored, so"
            " this case needs a replacement check for whatever it says instead",
        )
        patterns = {
            line.strip() for line in self.gitignore.splitlines() if not line.startswith("#")
        }
        self.assertIn(
            "trae_config.json",
            patterns,
            "docs/legacy_config.md promises .gitignore covers trae_config.json, and it no longer does --"
            " a reader's API key would be committable",
        )


if __name__ == "__main__":
    unittest.main()
