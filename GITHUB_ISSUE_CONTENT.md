# Standardize Logging Format Across All Python Files

## Issue Description

Currently, Python files in this repository use inconsistent logging formats. We need to standardize all logging configurations to use the following format specifier:

```python
format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s"
```

## Current State Analysis

### Root Logger Configuration Files (Entry Points):

1. **`registry/main.py:44-47`** - **Registry Application Entry Point**
   - **Current format**: `'%(asctime)s.%(msecs)03d - PID:%(process)d - %(filename)s:%(lineno)d - %(name)s - %(levelname)s - %(message)s'`
   - **Scope**: Configures root logger, affects all registry/* modules
   - **Status**: ❌ Needs update (different format structure)

2. **`auth_server/server.py:31-35`** - **Auth Server Entry Point**
   - **Current format**: `"[%(asctime)s] p%(process)s {%(filename)s:%(lineno)d} %(levelname)s - %(message)s"`
   - **Scope**: Configures root logger via basicConfig, affects auth server modules
   - **Status**: ❌ Needs update (brackets around timestamp, missing comma separators)

3. **`agents/agent.py:71-75`** - **Agent Entry Point**
   - **Current format**: `"%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s"`
   - **Scope**: Configures root logger via basicConfig, affects agent modules
   - **Status**: ✅ Already compliant

### MCP Server Entry Points (servers/ directory):

4. **`servers/mcpgw/server.py:24-28`** - **MCP Gateway Server**
   - **Current format**: `'%(asctime)s.%(msecs)03d - PID:%(process)d - %(filename)s:%(lineno)d - %(name)s - %(levelname)s - %(message)s'`
   - **Scope**: Standalone MCP server
   - **Status**: ❌ Needs update (different format structure, same as registry/main.py)

5. **`servers/currenttime/server.py:16-20`** - **Current Time MCP Server**
   - **Current format**: `'%(asctime)s.%(msecs)03d - PID:%(process)d - %(filename)s:%(lineno)d - %(name)s - %(levelname)s - %(message)s'`
   - **Scope**: Standalone MCP server
   - **Status**: ❌ Needs update (different format structure, same as registry/main.py)

6. **`servers/fininfo/server.py:17-21`** - **Financial Info MCP Server**
   - **Current format**: `'%(asctime)s.%(msecs)03d - PID:%(process)d - %(filename)s:%(lineno)d - %(name)s - %(levelname)s - %(message)s'`
   - **Scope**: Standalone MCP server
   - **Status**: ❌ Needs update (different format structure, same as registry/main.py)

7. **`servers/realserverfaketools/server.py:18-22`** - **Fake Tools MCP Server**
   - **Current format**: `'%(asctime)s.%(msecs)03d - PID:%(process)d - %(filename)s:%(lineno)d - %(name)s - %(levelname)s - %(message)s'`
   - **Scope**: Standalone MCP server
   - **Status**: ❌ Needs update (different format structure, same as registry/main.py)

### Files That Inherit Logging Format (No Changes Needed):

8. **`registry/auth/routes.py:13`**
   - **Current**: Uses `logging.getLogger(__name__)` - inherits from registry/main.py
   - **Status**: ✅ Will inherit correct format once main.py is updated

9. **`registry/search/service.py:14`**
   - **Current**: Uses `logging.getLogger(__name__)` - inherits from registry/main.py
   - **Status**: ✅ Will inherit correct format once main.py is updated

10. **`registry/health/routes.py:7`**
    - **Current**: Uses `logging.getLogger(__name__)` - inherits from registry/main.py
    - **Status**: ✅ Will inherit correct format once main.py is updated

11. **`registry/core/nginx_service.py:9`**
    - **Current**: Uses `logging.getLogger(__name__)` - inherits from registry/main.py
    - **Status**: ✅ Will inherit correct format once main.py is updated

### Files Without Logging:

12. **`registry/core/schemas.py`**
    - **Status**: ✅ No logging configuration needed (data models only)

13. **`registry/core/config.py`**
    - **Status**: ✅ No logging configuration needed (configuration only)

## Implementation Requirements

### Target Format Specification:
```python
format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s"
```

### Expected Output Format:
```
2025-06-15 17:48:37,p12345,{server.py:123},INFO,Server started successfully
```

## Files Requiring Changes Summary:

**Total files needing updates: 6** (Entry points only)

### Main Application Entry Points:
1. `registry/main.py` - Format modification (affects all registry/* modules)
2. `auth_server/server.py` - Format modification (affects auth server modules)

### MCP Server Entry Points:
3. `servers/mcpgw/server.py` - Format modification (standalone server)
4. `servers/currenttime/server.py` - Format modification (standalone server)
5. `servers/fininfo/server.py` - Format modification (standalone server)
6. `servers/realserverfaketools/server.py` - Format modification (standalone server)

**Already Compliant:**
- `agents/agent.py` - Already uses target format ✅

**Note**: Files using `logging.getLogger(__name__)` will automatically inherit the correct format once their respective entry points are updated, thanks to Python's logging hierarchy. The MCP servers in the `servers/` directory are standalone applications that each configure their own logging.

## Benefits

- **Consistency**: Uniform log format across all components
- **Parsing**: Easier automated log parsing and analysis
- **Debugging**: Consistent structure for troubleshooting
- **Monitoring**: Standardized format for log aggregation tools

## Acceptance Criteria

- [ ] All Python files use the standardized logging format
- [ ] Existing functionality remains unchanged
- [ ] Log output follows the expected format pattern
- [ ] No breaking changes to current logging behavior

## Labels
`enhancement`, `logging`, `maintenance`

## Priority
Medium