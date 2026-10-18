# HEALTHSYNC-AI frontend and reminder fixes

## Included

- Fixed the React input focus bug: `Panel`, `Heading`, and `Empty` were declared inside `App`, which recreated component types on every state update and caused focused inputs/textareas to unmount after each keystroke. They are now stable module-level components.
- Added a notification bell in the authenticated workspace header.
- The badge counts unread reminders due today or overdue. Opening the bell marks currently displayed notifications as seen in browser storage, so the unread badge clears and the notifications disappear from the unread list.
- Notification read state is stored per account in the browser.
- Responsive CSS prevents horizontal overflow, allows textareas to resize, breaks long OCR/code content, and avoids mobile browser input zoom.
- Added a backend reminder email worker that checks every 60 seconds and emails the registered user's email address when an open reminder becomes due. Successful deliveries are logged as `reminder_email_sent` audit events and deduplicated by reminder ID and due date. Vaccination next-due dates are synchronized to reminders by the existing vaccination API.

## Enable reminder email

Set these variables in the project root `.env` (do not commit real credentials):

```dotenv
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USER=your-registered-sender@gmail.com
SMTP_APP_PASSWORD=your-google-app-password
SMTP_FROM=your-registered-sender@gmail.com
```

Restart the backend/container after updating `.env`. The backend must remain running for scheduled delivery. If SMTP is missing or invalid, in-app reminders still work but email delivery will not.

## Validation performed

- Python `compileall`: passed.
- Backend pytest: 22 passed.
- TypeScript JSX transpilation syntax check for `src/App.jsx` and `src/main.jsx`: passed.
- Full Vite production build was not run because dependency installation timed out in this environment.

## Prototype note

The notification read state is browser-local, not synchronized across devices. The email send ledger uses the existing audit-event table to avoid adding a schema migration; for production deployment, move delivery status into a dedicated notification table and run the scheduler as a separate durable worker.
