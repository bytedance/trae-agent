# Fix Rich Markup Error in CLI

## Description
Fixes the issue where CLI crashes with `rich.errors.MarkupError` when printing error messages containing special characters like `[` or `]`.

## Root Cause
The CLI was using `console.print()` with formatted strings containing user-provided data that may include special characters. Rich tries to parse these as markup, causing crashes.

## Solution
Added `markup=False` parameter to all `console.print()` calls that format user-provided data, preventing Rich from parsing the content as markup.

## Changes Made
Modified `trae_agent/cli.py`:
- Added `markup=False` to 11 console.print() calls that format user-provided data
- Maintains all existing functionality and color formatting

## Testing
Created `test_markup_fix.py` to reproduce and verify the fix:
- Demonstrates the original issue would fail with MarkupError
- Verifies the fixed version handles error messages with square brackets correctly

## Impact
- Minimal code changes (only added `markup=False` parameter)
- Maintains backward compatibility
- Preserves color formatting while preventing markup parsing
- No breaking changes to existing functionality

## Verification
1. Run `python test_markup_fix.py` to see the original issue and the fix in action
2. The script will show that the fixed version handles error messages with square brackets correctly