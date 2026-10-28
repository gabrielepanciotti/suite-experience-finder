import { expect, test } from "vitest";

import App from "./App";

test("renders the application root", () => {
  expect(App()).toBeTruthy();
});
