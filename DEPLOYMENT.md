# Deployment quick guide (Render)

1. Push the project to a GitHub repository.
2. In Render, create a Web Service from that repository.
3. Select Docker as the runtime; Render detects `Dockerfile`.
4. Add environment variable `SECRET_KEY` with a long random value.
5. Set Health Check Path to `/health` and deploy.
6. Test `/`, `/health`, and both prediction forms on the generated Render URL.

The container build generates datasets and trains models, so the model artifacts are included in the deployed image. SQLite is suitable for a local/demo prototype; on ephemeral hosting its data may be lost when the instance is replaced. For persistent multi-user deployment, configure a persistent disk or a managed database and add authentication, privacy controls and input validation before collecting personal information.
