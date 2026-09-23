# Agent Instructions

## Environment Files

- Do not create, edit, overwrite, delete, rename, copy, print, or expose values from `.env` files.
- This includes `.env`, `.env.*`, `backend/.env`, frontend environment files, and production environment files.
- Treat all environment files as user-managed and containing secrets.

## Git And Deployment

- After every completed code change, run focused validation when available.
- Commit only the files changed for the requested task and push the commit to GitHub.
- Do not include unrelated user changes or generated files in a commit.
- In the final response, provide the exact server update command for the pushed change.
- For production updates, use the repository directory and the production environment file:

```bash
cd /opt/apps/mysub
git pull
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```