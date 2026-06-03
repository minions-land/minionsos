# README.md Fix Plan

## Critical Sections to Fix

### 1. Architecture (line 127-161) - REWRITE
Current: Shows Noter/Coder/Writer roles
Target: Show gru/ethics/expert v23 architecture

### 2. Configure (line 264-285) - UPDATE
Current: "Noter cadence and model, draft thresholds" / "for Coder"
Target: Remove Noter references, change Coder → Expert

### 3. Run (line 287-330) - UPDATE  
Current: `./noter <port>` command examples
Target: Clarify as project observer, not a Role

### 4. Roles (line 332-365) - REWRITE
Current: Table with Noter/Coder/Writer
Target: Three-role table (gru/ethics/expert) from CLAUDE.md

### 5. Skill family (line 366-388) - UPDATE
Current: "Noter's skill-curator-loop", "Noter proposes"
Target: Update autonomous evolution ownership

### 6. MCP Surface (line 389-555) - UPDATE
Current: Sections for "Coder", "Writer", "Noter"
Target: Remove role-specific headers, update tool descriptions

### 7. Runtime Project Structure (line 556-602) - UPDATE
Current: Branch layout with noter/, coder/, writer/
Target: Update to main/, ethics/, expert-<slug>/

### 8. Chinese sections (line 694-1322) - MIRROR ALL ABOVE
Same fixes for Chinese version

## Reference (from CLAUDE.md line 209-210)
- **Ethics**: memory curator (Draft→Book), evidence auditor — absorbed Noter duties
- **Expert**: general worker (code, experiments, paper drafting) — absorbed Coder/Writer duties
