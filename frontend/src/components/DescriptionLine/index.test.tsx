import { render } from "@testing-library/react"
import { DescriptionLine } from "."

describe('DescriptionLine', () => {
  it("Should display the given name", () => {
    const {container} = render(<DescriptionLine name="Test Name" details="_"/>)
    expect(container.textContent).toContain('Test Name');
  });

  it("Should display the given details", () => {
    const {container} = render(<DescriptionLine name="_" details="Test Details"/>)
    expect(container.textContent).toContain('Test Details');
  });
});
