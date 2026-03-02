# TODO: UI Component Fixes

This document provides a comprehensive task list for fixing the issues identified in `ISSUES_ANALYSIS.md`.

## Priority 0 (Critical - Fix Immediately)

### P0-1: Fix Duplicate Token Badge Rendering
**Status:** 🔴 Not Started  
**Assigned to:** TBD  
**Estimated Time:** 4-6 hours

**Tasks:**
- [ ] Add memoization/caching to `render_token_badges()` component using Streamlit's `@st.cache_data` or session state
- [ ] Implement component key management to prevent duplicate rendering
- [ ] Add guard conditions to prevent unnecessary state updates in `render_identity_selector()`
- [ ] Refactor `check_and_renew_tokens()` to only run when necessary (debounce/throttle)
- [ ] Add render counter/debug logging to identify all render triggers
- [ ] Review and optimize all `st.rerun()` calls to ensure they're necessary
- [ ] Test with multiple tabs open to ensure no cross-tab rendering issues

**Files to Modify:**
- `ui/app.py` - Line 69: Conditional token renewal check
- `ui/components/token_badges.py` - Lines 11-25, 80-113: Add memoization and guards
- `ui/components/auto_renew.py` - Lines 61-88: Add debouncing logic

**Acceptance Criteria:**
- [ ] Only one token badge component visible per token type
- [ ] No duplicate DOM elements in browser inspector
- [ ] Component renders only when token state actually changes
- [ ] Performance metrics show reduced render count

---

### P0-2: Fix Missing Default Model Configuration
**Status:** 🔴 Not Started  
**Assigned to:** TBD  
**Estimated Time:** 3-4 hours

**Tasks:**
- [ ] Add proper error handling in `ui/app.py:78-86` for model defaults loading
- [ ] Add validation to ensure defaults are loaded before allowing agent runs
- [ ] Implement proper initialization sequence for model defaults
- [ ] Add user-friendly error messages when defaults cannot be loaded
- [ ] Add retry logic for failed API calls
- [ ] Add loading state indicators during defaults fetch
- [ ] Ensure `defaults_loaded` flag is properly set in all code paths

**Files to Modify:**
- `ui/app.py` - Lines 78-86: Add error handling and validation
- `ui/views/models.py` - Lines 176-206: Improve error messaging
- `ui/views/agents.py` - Lines 46-81: Add validation checks
- `ui/state.py` - Lines 207-234: Add validation helpers

**Acceptance Criteria:**
- [ ] Model defaults load successfully on app startup
- [ ] Clear error messages shown if defaults cannot be loaded
- [ ] Users cannot create agent runs without defaults configured
- [ ] Proper loading states displayed during initialization

---

### P0-3: Fix Excessive Re-rendering
**Status:** 🔴 Not Started  
**Assigned to:** TBD  
**Estimated Time:** 5-6 hours

**Tasks:**
- [ ] Implement debouncing for `check_and_renew_tokens()` (max once per 60 seconds)
- [ ] Add state update guards to prevent unnecessary reruns
- [ ] Refactor `render_identity_selector()` to avoid state mutation during render
- [ ] Implement proper state update patterns (batch updates where possible)
- [ ] Add render cycle detection to prevent infinite loops
- [ ] Review all `st.rerun()` calls and remove unnecessary ones
- [ ] Add performance monitoring/logging for render cycles

**Files to Modify:**
- `ui/app.py` - Line 69: Add conditional check before renewal
- `ui/components/token_badges.py` - Lines 98-113: Refactor state updates
- `ui/components/auto_renew.py` - Lines 61-88: Add debouncing
- `ui/state.py` - Add state update helpers

**Acceptance Criteria:**
- [ ] Token renewal check runs maximum once per 60 seconds
- [ ] No cascading reruns triggered by state updates
- [ ] Performance metrics show reduced render count
- [ ] No infinite render loops

---

## Priority 1 (High - Fix Soon)

### P1-1: Fix Truncated Text Display
**Status:** 🔴 Not Started  
**Assigned to:** TBD  
**Estimated Time:** 1-2 hours

**Tasks:**
- [ ] Review time formatting logic in `_render_single_token_badge()` (lines 44-49)
- [ ] Ensure minutes are always displayed when hours > 0
- [ ] Fix string formatting to prevent truncation: `f"{hours}h {minutes}m"` should always show both parts
- [ ] Add CSS checks to ensure container width doesn't truncate text
- [ ] Test with various token expiration times (hours, minutes, seconds)
- [ ] Verify formatting consistency across all token types

**Files to Modify:**
- `ui/components/token_badges.py` - Lines 38-49: Fix time formatting logic

**Acceptance Criteria:**
- [ ] Time display always shows complete format (e.g., "23h 54m" not "23h 5")
- [ ] Consistent formatting across all token types
- [ ] No CSS truncation issues

---

### P1-2: Fix Provider Status Display Issues
**Status:** 🔴 Not Started  
**Assigned to:** TBD  
**Estimated Time:** 3-4 hours

**Tasks:**
- [ ] Add proper error handling in `_render_main_provider_status()` function
- [ ] Handle null/None cases for provider data gracefully
- [ ] Add meaningful error messages when provider data cannot be retrieved
- [ ] Implement fallback display for missing provider information
- [ ] Add retry logic for failed API calls
- [ ] Verify API response structure matches expected format
- [ ] Add loading states during provider data fetch

**Files to Modify:**
- `ui/views/models.py` - Lines 293-335: Improve error handling
- `ui/api.py` - Add error handling for provider API calls

**Acceptance Criteria:**
- [ ] Provider status displays correctly when data is available
- [ ] Clear error messages shown when provider data unavailable
- [ ] No "Unknown" or "N/A" displayed when providers exist
- [ ] Proper loading states shown during data fetch

---

## Priority 2 (Medium - Fix When Possible)

### P2-1: Improve Token Display Information
**Status:** 🔴 Not Started  
**Assigned to:** TBD  
**Estimated Time:** 2-3 hours

**Tasks:**
- [ ] Improve scope display clarity (make "+1" more descriptive)
- [ ] Add tooltip/help text explaining scope truncation
- [ ] Ensure `masked_token` property is always available and correctly formatted
- [ ] Add option to expand/collapse full token information
- [ ] Verify token masking security (proper redaction)
- [ ] Add timestamp display for token creation/expiration

**Files to Modify:**
- `ui/components/token_badges.py` - Lines 68-77: Improve scope display
- `ui/state.py` - Lines 36-40: Verify token masking

**Acceptance Criteria:**
- [ ] Scope display is clear and informative
- [ ] Token masking works correctly
- [ ] Users can access full token information when needed

---

### P2-2: Improve Accessibility
**Status:** 🔴 Not Started  
**Assigned to:** TBD  
**Estimated Time:** 2-3 hours

**Tasks:**
- [ ] Fix duplicate content for screen readers (ensure single instance)
- [ ] Add proper ARIA labels to all components
- [ ] Verify tab panel roles are correct
- [ ] Test with screen reader software
- [ ] Add keyboard navigation support
- [ ] Ensure color contrast meets WCAG standards

**Files to Modify:**
- `ui/components/token_badges.py` - Add ARIA labels
- `ui/app.py` - Verify accessibility attributes

**Acceptance Criteria:**
- [ ] No duplicate content for screen readers
- [ ] All components have proper ARIA labels
- [ ] Keyboard navigation works correctly
- [ ] WCAG compliance verified

---

### P2-3: Add Component Memoization Strategy
**Status:** 🔴 Not Started  
**Assigned to:** TBD  
**Estimated Time:** 3-4 hours

**Tasks:**
- [ ] Implement memoization for expensive components using Streamlit caching
- [ ] Add cache invalidation strategy for state-dependent components
- [ ] Document caching strategy in code comments
- [ ] Add cache monitoring/logging
- [ ] Test cache effectiveness with performance metrics

**Files to Modify:**
- `ui/components/token_badges.py` - Add memoization decorators
- `ui/components/auto_renew.py` - Add caching where appropriate

**Acceptance Criteria:**
- [ ] Components only re-render when dependencies change
- [ ] Cache invalidation works correctly
- [ ] Performance improvements measurable

---

## Testing Requirements

### Unit Tests
- [ ] Test token badge rendering with various token states
- [ ] Test state update logic to prevent unnecessary reruns
- [ ] Test time formatting with various expiration times
- [ ] Test model defaults loading and error handling
- [ ] Test provider status display with various data states

### Integration Tests
- [ ] Test complete app flow with token renewal
- [ ] Test agent run creation with and without defaults
- [ ] Test provider management workflow
- [ ] Test multiple tab interactions

### Performance Tests
- [ ] Measure render count before/after fixes
- [ ] Measure API call frequency
- [ ] Measure memory usage with duplicate components
- [ ] Load testing with multiple concurrent users

---

## Implementation Notes

### State Management Best Practices
1. **Never mutate state during render** - Use callbacks or event handlers
2. **Batch state updates** - Group related updates together
3. **Use session state keys** - Ensure unique keys for all components
4. **Debounce expensive operations** - Token renewal, API calls, etc.

### Component Rendering Best Practices
1. **Use component keys** - Prevent duplicate rendering
2. **Memoize expensive computations** - Use `@st.cache_data` or `@st.cache_resource`
3. **Conditional rendering** - Only render when data is available
4. **Loading states** - Show loading indicators during async operations

### Error Handling Best Practices
1. **Never fail silently** - Always show user-friendly error messages
2. **Handle all API errors** - Check success flags and handle errors
3. **Validate data before use** - Check for None/null before accessing properties
4. **Provide fallback UI** - Show meaningful placeholders when data unavailable

---

## Progress Tracking

**Overall Progress:** 0% Complete (0/11 tasks started)

**Priority Breakdown:**
- P0 (Critical): 0/3 complete
- P1 (High): 0/2 complete  
- P2 (Medium): 0/3 complete

**Estimated Total Time:** 25-35 hours

---

## Related Documentation

- `ISSUES_ANALYSIS.md` - Detailed issue analysis
- `ui/README.md` - UI component documentation
- Streamlit caching documentation: https://docs.streamlit.io/library/advanced-features/caching

---

## Notes

- All fixes should be backward compatible
- Consider creating feature flags for major refactoring
- Document any breaking changes
- Update tests after each fix
- Code review required for all changes

