# Included OCR model

`backend/models/tessdata/eng.traineddata` is the English Tesseract OCR language model (traineddata) included so OCR works inside the Docker image without downloading a model at application startup. The backend Dockerfile copies this file into the image, and `TESSDATA_DIR` points PyTesseract to it.

- Language: English (`eng`)
- Format: Tesseract traineddata
- License: Apache License 2.0; see `LICENSES/TESSERACT-APACHE-2.0.txt`
- Use: optical character recognition only; extracted text may contain mistakes and must be checked against the original source.

Additional languages require their own traineddata files and updates to the OCR language configuration.
