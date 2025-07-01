for tests use first lint then test

```sh
make lint
make test FILE=tests/...
```

use formatter on your code

```sh
make format FILE=app/...
```

In your Python code generation, adhere to the "fail fast" principle:

1.  **If any error condition is met or expected, immediately raise a relevant Python exception (e.g., ValueError, TypeError, FileNotFoundError).** Do not attempt to return a default value or continue execution if a problem is detected.
2.  **Only if the operation completes successfully and without any detected problems, return the expected result.**

**Why it works:**

- **Direct and unambiguous:** Clearly states the desired behavior for both error and success cases.
- **Emphasizes exceptions for errors:** Explicitly tells the LLM to use `raise`.
- **Discourages fallback values:** Prevents the LLM from returning `None`, empty lists, or 0 when an error occurs.
