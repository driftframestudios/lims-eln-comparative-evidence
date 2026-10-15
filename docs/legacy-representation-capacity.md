# Legacy representation capacities

Native comparison, observed-evidence admission, calibration, and simulated
closure intake share a dependency-free representation gate. The prepared
container uses that same native loader and carries the gate in its source
profile. `contract_v1` continues to own wire shape, duplicate-key and finite-number
semantics; `legacy_json` owns the resource allowance before recursive consumers
and detached copies. Administrative study and report receivers retain their
separate contracts.

| Capacity | Legacy input | Expanded report |
| --- | ---: | ---: |
| Encoded JSON bytes | 1 MiB | 16 MiB |
| Values plus member names | 20,000 | 400,000 |
| Container depth, counting the root | 32 | 40 |
| One string, UTF-8 bytes | 64 KiB | 64 KiB |
| Aggregate strings and names, UTF-8 bytes | 256 KiB | 8 MiB |
| One member name, UTF-8 bytes | 256 | 256 |
| Integer magnitude, bits | 2,048 | 2,048 |

A 2,048-bit integer uses at most 617 decimal digits, fitting beneath Python's
[minimum configurable 640-digit conversion limit](https://docs.python.org/3.12/library/stdtypes.html#integer-string-conversion-length-limitation) while preserving the host's
configuration. This keeps admitted integer conversion stable across supported
interpreter settings.

The supported input fixtures currently peak below 22 KiB. The input allowance
leaves space for result extensions while bounding the work of their consumers.
The report allowance covers repeated comparison rows and source records;
`comparison.html` has a separate 64 MiB byte limit. A fixture with a full 64 KiB
result string exercises input, envelope admission, comparison, JSON/HTML writing,
and saved-report verification. Applications needing larger evidence can select
an explicitly reviewed successor capacity.

File intake uses a concrete regular file, checks its stated size, and reads at
most the byte allowance plus one before decoding. UTF-8 and container depth are
checked before JSON parsing. Decoded Python values receive an iterative walk
before copying: cycles receive a capacity result, and repeated references are
charged each time they would expand into JSON. Python inputs receive the compact
UTF-8 JSON byte budget, including string escapes and punctuation; a file's
allowance also includes its actual whitespace and encoding bytes.

`RepresentationCapacityError`, a `ContractBoundaryError`, supplies a fixed
`legacy_*` code for byte, value, depth, string, aggregate-text, integer, cycle,
or Unicode capacity. Envelope capacity admission retains this typed category before shape validation.
Regular-file
admission retains the shared reader's `ReportArtifactError`. Error messages
identify the recovery category while input values stay with their caller.

The compatibility adapter creates one detached snapshot, validates a shallow
shared-contract projection, and freezes the retained richer envelope. Its shared
projection owns fields that validation trims; the richer snapshot preserves the
original values. Public adapters continue to validate caller-owned inputs, and
returned snapshots remain independently mutable or immutable as their APIs
specify.

Saved-report intake inspects at most three directory entries to establish its
exact two-file membership, then applies the named JSON/HTML byte limits. The
staged producer verifier keeps its exact prepared byte counts. Report writing
checks representation and serialized byte capacity before publication. A
capacity rejection leaves the destination's previous complete pair available.
Input admission establishes input capacity; the expanded report has its own
capacity decision before publication.
Pages validates generated report JSON with that report allowance. Input
fixtures and projection manifests retain the input allowance.

For B input bytes, N expanded values/member names, D container depth, K integer
bits, P compared paths and H output bytes, admission adds a bounded byte/depth
pass and an O(N + text bytes) walk with integer conversion work dependent on K.
The walk retains O(D) traversal state. It visits repeated references by expanded
population, stopping at the allowance rather than copying the expansion.
The focused allocation observation excludes the caller's already allocated
input and measures less than 128 KiB of working allocation while rejecting a
million-value repeated-reference expansion. It establishes that bounded walk's
working storage, rather than a peak-memory claim for the entire comparison.

Compatibility preparation reduces three detached whole-document copies to one.
Normalization, path construction/traversal, JSON key sorting, integer arithmetic,
rendering and output-byte allocation keep their existing costs. Output generation
retains bounded intermediate strings before the final byte check. This change
improves admission and temporary-copy ownership; it makes no general asymptotic
performance claim for the whole comparison.
