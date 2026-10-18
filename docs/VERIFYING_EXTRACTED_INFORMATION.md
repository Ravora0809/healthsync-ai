# Verify extracted medical information

HEALTHSYNC-AI now provides a per-item **Verify against original** workflow for extracted lab candidates, medicines, test results, and care instructions.

## User workflow

1. Open **Medical records** and click **Analyze** on a record. Agree to OpenRouter processing only if you want hosted structured extraction; canceling the consent prompt runs local evidence review only.
2. In the Evidence Engine / AI medical document analysis, compare every medicine, result, and instruction with the original document.
3. Click **Verify against original** only after comparing the item with the source. This saves that the user reviewed it; it is not medical or clinician approval.
4. If the transcription is wrong, choose **Edit & verify**, correct the editable values to match the original, optionally add a note, and save. The stored source excerpt is kept unchanged for provenance.
5. Use **Mark incorrect** when the extracted item is not present or is wrong. That status is retained in the record and included in the assistant's retrieved context.
6. The same controls are available when expanding analyzed records from the **Medical records** section. Review status is saved to PostgreSQL through the record's JSON extraction payload and an audit event.

## API

`POST /api/evidence/verify/{record_id}`

Request body:

```json
{
  "item_type": "medicine",
  "index": 0,
  "status": "user_verified",
  "corrected_values": {"dose_as_written": "1 tablet"},
  "note": "Compared with original prescription"
}
```

`item_type` is one of `medicine`, `test`, `instruction`, or `candidate`. Instruction updates also require a `section` such as `food`, `exercise`, `precautions`, `temperature`, `medicine_storage`, or `hospital_follow_up`. Omitting `corrected_values` simply records the review. Editable fields are allow-listed by item type; `source_excerpt` cannot be changed through this endpoint.

Statuses saved on the individual item:

- `user_verified`: user compared the extracted value with the original.
- `corrected_and_user_verified`: user corrected one or more values and then saved the review.
- `rejected_as_incorrect`: user says the extracted item is incorrect or not present.

Record-level states (`pending_review`, `partially_reviewed`, `reviewed_by_user`, `reviewed_with_rejections`) summarize the user's review activity only. They do not indicate that a clinician has approved the record or that the medicine is safe.

## Safety and scope

- OCR and model extraction remain fallible. The button is a human review step, not an automatic proof of truth.
- The source excerpt is preserved unedited. A corrected transcription can therefore differ from the excerpt; users should inspect the original image/PDF.
- Medication doses, units, frequency, duration, and instructions should be confirmed by the prescribing clinician/pharmacist when handwriting is ambiguous.
- User-verified status means only that the user says they compared the item with the original. It does not mean the clinical meaning, diagnosis, or treatment was verified.
- AI Assistant prompts are instructed to distinguish user-reviewed items from clinician-approved facts and not present `rejected_as_incorrect` items as valid current facts.
