# MinionsOS Repository Audit Report
Generated: 2026-06-03

## Executive Summary

Systematic audit of MinionsOS repository to achieve EACN3-level code quality and cleanliness.

### Completed Actions
1. ✅ Removed unused MCP servers: `mcp-servers/codegraph/` (180MB) and `mcp-servers/graphify/` (231MB)
   - These were already disabled in code (47cfe42) but left empty node_modules directories

### Critical Issues Found

## 1. OVERCLAIM: README.md Architecture Mismatch (CRITICAL)

**Severity**: HIGH - User-facing documentation claims outdated architecture

**Problem**: README.md (both English and Chinese) describes a 5-role system (Gru, Noter, Coder, Writer, Ethics, Expert) but v23 rebuild consolidated to 3 roles (Gru, Ethics, Expert).

**Locations**:
- Line 138-147: Architecture diagram shows `Coder`, `Writer`, `Noter` branches
- Line 251: `./mos restart <port> --role coder`
- Line 270-271: "Noter cadence", "for Coder"
- Line 291-308: `./noter <port>` command and Noter terminal description
- Line 332-342: Roles table with Noter/Coder/Writer
- Line 358-380: Autonomous evolution describes Noter proposing
- Line 432-433: `mos_await_events` for Coder/Writer, `mos_noter_wait`
- Line 498: "Coder — experiment execution"
- Line 524: "denied to Noter"
- Line 532: "Writer — paper search"
- Line 566-573: Branch layout with noter/, coder/, writer/
- Line 791-797: Chinese architecture diagram (same issue)
- Line 976-1023: Chinese roles table and descriptions

**Actual v23 Architecture** (from CLAUDE.md):
- **Gru**: orchestrator, human interface, project lifecycle
- **Ethics**: memory curator (Draft→Book), evidence auditor, absorbed Noter duties
- **Expert**: general worker (code, experiments, paper drafting), absorbed Coder/Writer duties

**Impact**: 
- Users will try commands that don't work (`./noter <port>`)
- Misunderstand system capabilities
- Confusion about role responsibilities

**Fix Required**: Rewrite entire README Architecture, Roles, Run, and MCP sections to reflect v23 three-role system.

## 2. INCONSISTENT: `./noter` Command Still Exists

**Location**: Root launcher `./noter`
**Status**: Command exists but its description was updated to "read-only project observatory terminal"
**Issue**: README still describes it as "Noter terminal" with Noter-specific features
**Fix**: Update README to describe it as generic project observer, not a Role

## 3. INCONSISTENT: Config Documentation

**Location**: README line 270-271
**Claims**: 
- "Noter cadence and model"
- "for Coder"

**Actual** (from earlier cleanup):
- `noter_periodic_interval` and `noter_report_interval` were REMOVED as dead config
- Experiment tools are for Expert, not Coder

**Fix**: Update config descriptions

## 4. DEADCODE: `docs/` Directory (gitignored but exists)

**Location**: `docs/` at root
**Status**: Entire directory gitignored (line 150 .gitignore: `docs/`)
**Contents**: 
- `docs/Reconstruction/` - rebuild docs
- `docs/Skill_Summary.md` - also explicitly gitignored
- `docs/report/` - also explicitly gitignored
- `docs/research/`
- `docs/integrations/`
- `docs/memory-verified-claims.md`

**Question**: Why gitignore the entire `docs/` if some files should be tracked?
**Recommendation**: Either commit valuable docs or delete entirely. Mixed state is confusing.

## 5. OBSOLETE: Workflow Plugins Placeholder

**Location**: `workflow-plugins/` directory
**Contents**: Only README.md and one example (`evoany/`)
**Status**: Minimal usage, unclear if active
**Recommendation**: Verify if this is used or just a placeholder

## 6. INCONSISTENT: MCP Server Registry

**Location**: `mcp-servers/README.md`
**Missing**: `codex-subagent` is listed in registry (line 13) but we need to verify it exists
**Action**: Verify all claimed MCP servers actually exist and work

## Priority Cleanup Plan

### Phase 1: Critical Documentation (User-Facing)
1. **README.md Architecture section** - rewrite to v23 three-role system
2. **README.md Roles table** - update responsibilities
3. **README.md Run section** - fix command examples
4. **README.md MCP Surface** - remove Coder/Writer/Noter tool sections
5. **README.md Chinese sections** - mirror all English fixes

### Phase 2: Dead Code Removal
1. Verify and document `docs/` directory status
2. Check `workflow-plugins/` actual usage
3. Audit `MANUAL/` for retired role references

### Phase 3: Code Verification
1. Verify all MCP tools claimed in README actually exist
2. Check experiment execution ownership (Expert vs Coder claims)
3. Verify all config options in README match actual gru.yaml.example

### Phase 4: Test Coverage
1. Ensure tests don't reference retired roles
2. Verify smoke tests cover current architecture

## Recommendations

1. **Single Source of Truth**: CLAUDE.md is correct. Use it as reference for README updates.
2. **Version Documentation**: Add a v23 migration guide explaining the consolidation.
3. **Consistency Check**: Add a linter/test that checks README role names against actual role directories.
4. **Minimize Docs**: Follow EACN3 model - less is more. Remove speculative/aspirational content.
