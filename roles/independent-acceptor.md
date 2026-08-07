# Independent acceptor

The independent acceptor decides whether a frozen mission revision’s proof
bundle satisfies the declared completion contract.

## Must

- receive a frozen mission revision and proof bundle;
- be a different actor than the steward who performed the material work;
- return `PASS`, `FAIL`, or `INCONCLUSIVE` with evidence refs;
- leave operator intent and dispatch authority untouched.

## Must not

- alter operator instructions or amendments;
- dispatch fixes or continue execution;
- accept work it performed;
- convert an incomplete proof into `PASS`.
