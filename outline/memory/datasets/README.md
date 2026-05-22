# Benchmark Datasets

Staged sample data for MinionsOS memory evaluation.

## LoCoMo
- Source: snap-research/locomo (git clone)
- File: locomo/sample_5.json  (5 conversations, from locomo10.json)
- Full dataset: locomo_repo/data/locomo10.json (10 conversations, ~2.8MB)
- Format: JSON array; each item has keys: qa, conversation, event_summary, observation, session_summary, sample_id

## MemBench  
- Source: import-myself/Membench (git clone)
- File: membench/sample_5.json (5 role threads + 5 event threads)
- Full dataset: membench_repo/MemData/FirstAgent/ (multiple JSON files by task type)
- Format: JSON with top-level keys: roles, events; each item has: tid, message_list, QA

## MemoryAgentBench
- Repo does NOT contain benchmark data — it is an evaluation framework
- Dataset location: HuggingFace (HUST-AI-HYZ/MemoryAgentBench)
- To download: huggingface-cli download HUST-AI-HYZ/MemoryAgentBench --local-dir ./memoryagentbench/
- See DOWNLOAD_INSTRUCTIONS.md

## MemoryArena
- Not confirmed as an official benchmark — no paper or repo found
- Placeholder directory only
