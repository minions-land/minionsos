# MemoryAgentBench Dataset Download

The MemoryAgentBench GitHub repo (HUST-AI-HYZ/MemoryAgentBench) contains the evaluation 
framework code but NOT the benchmark data. The data is hosted on HuggingFace.

## Download commands

```bash
# Install HuggingFace CLI if needed
pip install huggingface-hub

# Download the dataset
huggingface-cli download HUST-AI-HYZ/MemoryAgentBench     --local-dir ./memoryagentbench/     --repo-type dataset

# OR with Python
python3 -c "
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id='HUST-AI-HYZ/MemoryAgentBench',
    repo_type='dataset',
    local_dir='./memoryagentbench/'
)
"
```

## Expected structure after download
memoryagentbench/
  ar_test.jsonl          # Accurate Retrieval
  ttl_test.jsonl         # Test-Time Learning
  lru_test.jsonl         # Long-Range Understanding
  sf_test.jsonl          # Selective Forgetting

## Sample (download first AR item only)
```bash
huggingface-cli download HUST-AI-HYZ/MemoryAgentBench ar_test.jsonl     --local-dir ./memoryagentbench/ --repo-type dataset
head -n 3 memoryagentbench/ar_test.jsonl
```
