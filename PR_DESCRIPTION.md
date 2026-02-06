## Fix Rich MarkupError in CLI Error Handling

### Problem
The Trae Agent CLI was crashing with `rich.errors.MarkupError` when exception messages contained special characters like square brackets (`[`, `]`). This occurred because rich was trying to parse these characters as markup tags when printing error messages.

### Root Cause
In `trae_agent/cli.py`, error messages were being printed using:
```python
error_text = Text(f"Error: {e}", style="red")
console.print(f"\n{error_text}")  # Could fail with MarkupError
```

When exception `e` contained brackets, rich would try to parse them as markup, causing crashes like:
- `MarkupError: closing tag '[/section]' doesn't match any open tag`

### Solution
Added `markup=False` parameter to `console.print()` calls when printing `Text` objects containing exception messages:

```python
error_text = Text(f"Error: {e}", style="red")
console.print(error_text, markup=False)  # Prevents MarkupError
```

### Changes Made
- **File**: `trae_agent/cli.py`
- **Lines fixed**: 4 locations where `console.print(error_text)` was called
- **Impact**: Minimal code change, no behavioral change, improved stability

### Testing
- Created comprehensive test scripts that verify the fix works
- Tested with various problematic strings containing brackets
- Confirmed error messages still display with red styling as intended
- Verified CLI no longer crashes on exception messages with special characters

### Verification
Run the provided test scripts:
```bash
python test_markup_fix.py
python demonstrate_markup_fix.py
```

Both should complete without errors, proving the fix is working correctly.

### Backward Compatibility
- ✅ No API changes
- ✅ No user-facing behavioral changes  
- ✅ Error messages maintain original styling
- ✅ Only prevents crashes, doesn't change functionality

This fix ensures the CLI remains stable when handling exceptions with special characters in their messages.