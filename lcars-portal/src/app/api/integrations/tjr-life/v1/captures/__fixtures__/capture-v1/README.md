# capture-v1 shared fixtures

Byte-identical copies of `Tests/fixtures/capture-v1/request-two-items.json` and `response-accepted.json`
in `timjardenross/TJR-Life-iOS`. The iOS tests assert that the app builds exactly this request and
accepts exactly this reply; `captures.test.ts` asserts that the route accepts this request and answers
in this shape. If either side changes the contract, both copies and both suites change together.
