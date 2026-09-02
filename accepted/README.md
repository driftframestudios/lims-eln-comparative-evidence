# Accepted namespace

The admission command writes observed, provenance-complete manifests here during
qualified workflows. Generated manifests stay outside ordinary source commits until
the evidence owner approves their redacted form.

This release keeps the namespace empty by design. Unit tests create observed and
accepted envelopes inside temporary directories to exercise the gate without
publishing an environment claim.

Raw artifacts remain in governed evidence storage. Each accepted manifest carries the
raw-artifact digest, protected locator, independent reviewer, classification, and
redaction disposition.
