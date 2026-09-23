import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import WorkflowStepper from './WorkflowStepper';

const STEP_NAMES = ['Open', 'In progress', 'Resolved', 'Closed', 'Archived'];

/**
 * The MUI label element for a step, found by its visible text.
 * MUI marks state with CSS classes: Mui-active, Mui-completed, Mui-error.
 * @param {string} name
 * @returns {HTMLElement}
 */
function stepLabel(name) {
  return screen.getByText(name).closest('.MuiStepLabel-root');
}

describe('WorkflowStepper', () => {
  it('shows all five steps', () => {
    render(<WorkflowStepper status="open" />);
    STEP_NAMES.forEach((name) => expect(screen.getByText(name)).toBeInTheDocument());
  });

  it('marks earlier steps complete and the current one active', () => {
    render(<WorkflowStepper status="resolved" />);
    expect(stepLabel('Open').querySelector('.Mui-completed')).not.toBeNull();
    expect(stepLabel('In progress').querySelector('.Mui-completed')).not.toBeNull();
    expect(stepLabel('Resolved').querySelector('.Mui-active')).not.toBeNull();
    expect(stepLabel('Closed').querySelector('.Mui-completed')).toBeNull();
  });

  it('shows a blocked ticket as an error on the "In progress" step', () => {
    render(<WorkflowStepper status="blocked" />);
    expect(stepLabel('In progress').querySelector('.Mui-error')).not.toBeNull();
    expect(screen.getByText('Blocked')).toBeInTheDocument();
    // Only that step is in error.
    expect(stepLabel('Open').querySelector('.Mui-error')).toBeNull();
  });

  it('does not show an error for tickets that are not blocked', () => {
    const { container } = render(<WorkflowStepper status="in_progress" />);
    expect(container.querySelector('.Mui-error')).toBeNull();
    expect(screen.queryByText('Blocked')).not.toBeInTheDocument();
  });

  it('shows every step complete for an archived ticket', () => {
    render(<WorkflowStepper status="closed" archived />);
    STEP_NAMES.forEach((name) => {
      expect(stepLabel(name).querySelector('.Mui-completed')).not.toBeNull();
    });
  });
});
