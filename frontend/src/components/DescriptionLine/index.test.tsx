import { render } from "@testing-library/react"
import { DescriptionLine } from "."

describe('DescriptionLine', () => {
  let container: HTMLElement;

  beforeEach(() => {
    const result = render(<DescriptionLine name="Test Name" details="Test Details"/>);
    container = result.container;
  });

  it("Should display the given name", () => {
    expect(container.textContent).toContain('Test Name');
  });

  it("Should display the given details", () => {
    expect(container.textContent).toContain('Test Details');
  });
});
