# Pod File Copy Scripts

This directory contains scripts to copy files from Kubernetes pods to your local machine.

## Scripts Available

### 1. `copy_pod_files.sh` - Interactive Version
Interactive script with user prompts and confirmations.

**Usage:**
```bash
./scripts/copy_pod_files.sh <pod_name>
```

**Example:**
```bash
./scripts/copy_pod_files.sh oats-backend-api-646df75585-wfrsm
```

**Features:**
- Checks if pod exists and is running
- Shows available pods if the specified pod is not found
- Prompts before overwriting existing directories
- Shows file count and directory structure
- Interactive confirmations at each step

### 2. `copy_pod_files_auto.sh` - Non-Interactive Version
Automated script for CI/CD or scripting environments.

**Usage:**
```bash
./scripts/copy_pod_files_auto.sh <pod_name> [force]
```

**Examples:**
```bash
# Copy files (fails if directory exists)
./scripts/copy_pod_files_auto.sh oats-backend-api-646df75585-wfrsm

# Force overwrite existing directory
./scripts/copy_pod_files_auto.sh oats-backend-api-646df75585-wfrsm force
```

**Features:**
- Non-interactive (no prompts)
- Force mode to overwrite existing directories
- Same validation as interactive version
- Suitable for automation and scripting

## What These Scripts Do

1. **Validate Pod**: Check if the specified pod exists and is accessible
2. **Check Status**: Verify pod is running (with warning for non-running pods)
3. **Create Directory**: Create `~/tmp_<pod_name>` directory locally
4. **Copy Files**: Use `kubectl cp` to copy all files from `pod:/app` to local directory
5. **Show Summary**: Display file counts and directory structure

## Output Directory Structure

Files are copied to: `~/tmp_<pod_name>/`

For example, if your pod is `oats-backend-api-646df75585-wfrsm`, files will be copied to:
`~/tmp_oats-backend-api-646df75585-wfrsm/`

## Prerequisites

- `kubectl` configured and accessible
- Pod must be running (or you can proceed with warnings)
- Write access to your home directory

## Error Handling

- Scripts exit with error code 1 on failure
- Clean up partial copies on failure
- Show helpful error messages and suggestions
- List available pods when specified pod is not found

## Notes

- Symlinks are skipped during copy (this is normal kubectl behavior)
- Large files may take time to copy
- The scripts preserve directory structure from the pod
- All files and directories from `/app` in the pod are copied
