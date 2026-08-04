# Evidence handling

Evaluation records declare evidence level, environment, data class, sources,
observation time, and limitations. This makes documented claims, configured results,
exercised scenarios, and operational observations legible as distinct kinds of
evidence.

Checked-in fixtures use synthetic content. Deidentified or redacted records may be
supplied at runtime when their handling permits repository processing. Raw regulated
records, secrets, credentials, and sensitive traces remain in their designated
systems; records reference them through protected or redacted locators.

Comparison profiles expose only the values explicitly listed in `reportable_paths`.
Other differing values appear as deterministic content digests. The source program
uses the report alongside scientific, Quality, Regulatory, security, commercial, and
operational evaluation practices.
