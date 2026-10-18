# Original medical document preview fix

The Medical records list now separates two actions:

- **Original** opens the stored image or PDF in a new browser tab using a Blob URL. It no longer triggers a download.
- **Download** explicitly downloads the original file.

The preview tab is opened synchronously from the user's click so popup blockers are less likely to interfere. The API call remains authenticated through the existing Axios client. The file stays under the existing owner-authorized download endpoint.

If the preview is blocked, allow pop-ups for the local HEALTHSYNC-AI origin (for example, `http://127.0.0.1:5173`) and retry.

## Apply

Replace `frontend/src/App.jsx` with the updated file in this archive, then restart the frontend:

```bash
cd frontend
npm run dev
```

If running through Docker Compose, rebuild/restart the frontend:

```bash
docker compose up --build -d frontend
```

The dependency installation/build could not be completed in this environment because `npm install` timed out. Test the preview using a PDF and an image in your local browser.
