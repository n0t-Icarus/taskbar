# doctest (vendored)

The unit-test framework for the Windows-free core (`src/core/`). Single header,
vendored rather than fetched, so a CI build needs no network beyond the checkout
and a clone reproduces exactly.

| | |
| --- | --- |
| Version | 2.4.11 |
| Source | https://raw.githubusercontent.com/doctest/doctest/v2.4.11/doctest/doctest.h |
| Licence | MIT (Copyright (c) 2016-2023 Viktor Kirilov) |
| SHA-256 | `44faa038e9c3f9728efbda143748d01124ea0a27f4bf78f35a15d8fab2e039fb` |

To verify the vendored copy is unmodified:

```sh
sha256sum third_party/doctest/doctest.h
```

Do not edit `doctest.h` by hand — it is generated upstream.
