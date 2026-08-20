# Publishing this project to GitHub

A step-by-step guide for getting this folder onto GitHub, written for
anyone who hasn't done it before. Run everything from inside this project
folder (the one with `config.py`, `README.md`, and this file in it).

## 1. Install Git (skip if you already have it)

Check first:

```bash
git --version
```

If that fails, install Git:
- **Windows:** https://git-scm.com/download/win
- **macOS:** `brew install git` (or install Xcode Command Line Tools)
- **Linux:** `sudo apt install git` (Debian/Ubuntu) or your distro's equivalent

## 2. Create the GitHub repository

1. Go to https://github.com/new
2. Pick a name (e.g. `bodymap-net`)
3. Leave it **empty** — do **not** tick "Add a README", "Add .gitignore", or
   "Add a license". This project already has all three; letting GitHub
   create its own would conflict with the ones already here.
4. Click **Create repository** and keep the page open — it shows the exact
   remote URL you'll need in step 4.

## 3. Turn this folder into a Git repository

```bash
git init
git add .
git status
```

Read the `git status` output before committing — it should list this
project's actual source files (`config.py`, `app/`, `model/`, `db/`,
`data/`, `tests/`, `README.md`, etc.). It should **not** list the
database file, trained checkpoints, or generated CSVs — those are already
excluded by `.gitignore`. If you see `db/bodymap.db`,
`model/checkpoints/*.pt`, or `data/processed/*.csv` in that list, stop and
check that `.gitignore` is actually present in this folder before
continuing.

```bash
git commit -m "Initial commit"
```

## 4. Connect it to GitHub and push

GitHub shows you this exact block after step 2 — copy it from there so the
URL matches your account/repo name. It looks like:

```bash
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo-name>.git
git push -u origin main
```

If you'd rather use SSH instead of HTTPS (no password prompt after the
first setup), use the SSH URL GitHub shows instead
(`git@github.com:<your-username>/<your-repo-name>.git`) — see GitHub's own
guide for setting up an SSH key if you haven't already:
https://docs.github.com/en/authentication/connecting-to-github-with-ssh

## 5. Verify

Refresh the repository page on GitHub. You should see the full file tree —
`README.md` renders automatically on the repo's front page. Click through
a few files to confirm nothing important got left out (compare against
`FILES.txt` in this folder if unsure).

## 6. Let people actually run it

Anyone who clones the repo needs to follow the **Build & run order**
section of `README.md` before the app will work — the trained models,
generated dataset, and database are intentionally not part of the repo
(see `.gitignore`), so they need to be built locally:

```bash
git clone https://github.com/<your-username>/<your-repo-name>.git
cd <your-repo-name>
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python data/data_generator.py
python model/dataset.py
python model/train_branches.py
python model/train_fusion.py
python app/app.py
```

## Updating the repo later

Once it's set up, pushing further changes is just:

```bash
git add .
git status              # sanity-check what's about to be committed
git commit -m "Describe what changed"
git push
```

## Common issues

- **`git push` asks for a username/password and rejects it** — GitHub
  removed password-over-HTTPS support. Either switch to SSH (step 4) or
  create a Personal Access Token and use that as the password:
  https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens
- **The database file or trained models show up in `git status`** — make
  sure you're running commands from this folder (so `.gitignore` is picked
  up) and that a file named exactly `.gitignore` (not `.gitignore.txt`)
  exists here.
- **"remote origin already exists"** — you already ran `git remote add
  origin ...` once. Either `git remote remove origin` and re-add it, or
  just use `git remote set-url origin <url>` to change it.
