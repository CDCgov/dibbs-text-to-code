# scripts/

## `aws_e2e.sh`

End-to-end smoke test for the deployed DIBBs TTC pipeline.

Given a "nonstandard test name" (e.g. `"Zucchini IgG"`), the script:

1. Templates `test_eicr.xml` with that name and fresh UUIDs for `<id>` and `<setId>`.
2. Uploads the canned schematron errors file to `s3://dibbs-text-to-code/ValidationResponseV2/`, then the templated eICR to `s3://dibbs-text-to-code/TextToCodeSubmissionV2/` — the eICR upload fires the TTC Lambda via an S3 → SQS event.
3. Tails CloudWatch logs for both `ttc-lambda` and `ttc-augmentation-lambda` in real time, with a pinned spinner, until each emits its `REPORT RequestId:` end-of-invocation marker.
4. Fetches and pretty-prints the resulting TTC metadata JSON (`TTCMetadataV2/`) and augmented eICR XML (`AugmentationEICRV2/`) from S3.

### Usage

```sh
./scripts/aws_e2e.sh "<nonstandard test name>"
```

Example:

```sh
./scripts/aws_e2e.sh "Zucchini IgG"
```

You must have AWS credentials available in the environment (e.g. via `aws sso login` or `AWS_PROFILE`) with permissions to write to the `dibbs-text-to-code` bucket and read CloudWatch logs in `us-east-2`.

## Dependencies

| Tool                       | Why                                                                                                                                                                                                           |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `bash`                     | Script interpreter (uses `[[`, arrays, `BASH_REMATCH`).                                                                                                                                                       |
| `aws` (CLI v2)             | S3 uploads, `s3api head-object` polling, `logs tail`.                                                                                                                                                         |
| `gum`                      | Styled banners, spinners, log levels (Charm TUI library).                                                                                                                                                     |
| `unbuffer` (from `expect`) | Wraps `aws logs tail` in a PTY so its output line-buffers when piped. The AWS CLI v2 is a PyInstaller bundle that ignores `PYTHONUNBUFFERED`, so without `unbuffer` log lines arrive in one burst at the end. |
| `jq`                       | Pretty-prints JSON log payloads and the TTC metadata output.                                                                                                                                                  |
| `python3`                  | Templates the eICR (regex substitutions for displayName, originalText, and UUIDs). Standard library only.                                                                                                     |
| `xmllint` (from `libxml2`) | Pretty-formats the augmented eICR XML output.                                                                                                                                                                 |
| `bat` _(optional)_         | Syntax-highlights the formatted XML. Falls back to plain output if missing.                                                                                                                                   |

### Install — macOS

All deps are available via Homebrew:

```sh
brew install awscli gum expect jq libxml2 bat
```

`python3` ships with macOS; if you want a newer one, `brew install python`.

### Install — Linux (Debian/Ubuntu)

```sh
# AWS CLI v2 — install from Amazon's bundle (the apt package is v1)
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip
unzip awscliv2.zip && sudo ./aws/install

# Charm gum — add their apt repo
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://repo.charm.sh/apt/gpg.key | sudo gpg --dearmor -o /etc/apt/keyrings/charm.gpg
echo "deb [signed-by=/etc/apt/keyrings/charm.gpg] https://repo.charm.sh/apt/ * *" \
    | sudo tee /etc/apt/sources.list.d/charm.list
sudo apt update && sudo apt install gum

# The rest are in the default repos
sudo apt install expect jq libxml2-utils python3 bat

# On Debian/Ubuntu the `bat` binary is named `batcat`; symlink it:
mkdir -p ~/.local/bin && ln -s /usr/bin/batcat ~/.local/bin/bat
```

For Fedora/RHEL, swap `apt` for `dnf` and use `libxml2` instead of `libxml2-utils`.

### Install — Windows (WSL with Homebrew)

From inside your WSL shell (Linuxbrew installs to `/home/linuxbrew/.linuxbrew`):

```sh
brew install awscli gum expect jq libxml2 bat
```

The script is bash-only — run it from inside WSL, not from PowerShell or `cmd.exe`. Make sure your AWS credentials are configured inside WSL (`aws configure` or `aws sso login` from the WSL shell).

## Test fixtures

- `test_eicr.xml` — minimal eICR document used as the template input.
- `test_schematron_errors.xml` — canned schematron validation report uploaded alongside the eICR.

The script reuses the same generated filename across every S3 prefix; that's how the TTC and augmentation Lambdas correlate the schematron report, source eICR, and output objects for one invocation.
