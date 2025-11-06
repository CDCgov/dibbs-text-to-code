import { render } from "@testing-library/react"
import { Panel } from "."

describe('DescriptionLine', () => {
  let container: HTMLElement;
  const testTitle = 'Test Title';
  const testContent = 'Test Content'

  beforeEach(() => {
    const result = render(<Panel title={testTitle}>{testContent}</Panel>);
    container = result.container;
  });

  it("Should display the given title", () => {
    expect(container.textContent).toContain(testTitle);
  });

  it("Should display the given content", () => {
    expect(container.textContent).toContain(testContent);
  });
});
