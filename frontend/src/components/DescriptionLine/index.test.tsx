import { render } from '@testing-library/react';
import { DescriptionLine } from '.';

describe('DescriptionLine', () => {
  let container: HTMLElement;
  const testName = 'Test Name';
  const testDetails = 'Test Details';

  beforeEach(() => {
    const result = render(
      <DescriptionLine name={testName} details={testDetails} />
    );
    container = result.container;
  });

  it('Should display the given name', () => {
    expect(container.textContent).toContain(testName);
  });

  it('Should display the given details', () => {
    expect(container.textContent).toContain(testDetails);
  });
});
