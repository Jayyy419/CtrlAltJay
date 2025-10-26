# CtrlAltJay Portfolio

## Virtual Environment
Creating a virtul environment:
```py -m venv venv```

Activating the virtual environment:
```venv\Scripts\activate```

Deactivate the virtual environement:
```deactivate```

If using Github, create a .gitignore file and include:
```venv/```

## Pip
Upgrading pip:
```py -m pip install --upgrade pip```

Installing packages:
```pip install <example>```

Finding location of packages:
```where <example>```

Creating the requirements.txt of project dependecies:
```pip freeze > requirements.txt```

Installing project dependecies using requirements.txt:
```pip install -r requirements.txt```

## Git
Adding all files:
```git add .```

Adding only modified files:
```git add -u```

Uploading files:
```bash
git commit -m "example"
git pull
git push
git status
```

Merging to Main:
```bash
git checkout main
git merge <branch-name>
git push -f

git pull
git checkout <branch-name>
git pull
git merge main
git push
```

Connecting between repositories:
```git push --set-upstream origin <branch-name>```

Pushing to another branch:
```git push origin <branch-name>```

Uncommitting messages:
```git reset --soft HEAD~1```

Finding lost commits (Finding specific contents of files):
```bash
git fsck --lost-found
git show <commit-number>
git rebase <commit-number>
```

Finding lost commits (Find specific commits):
```git reflog```

Recovering lost commits:
```git branch <branch-name> <commit-hash>```

Verifying log:
```git log```
