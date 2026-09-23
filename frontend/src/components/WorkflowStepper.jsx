import PropTypes from 'prop-types';
import Step from '@mui/material/Step';
import StepLabel from '@mui/material/StepLabel';
import Stepper from '@mui/material/Stepper';
import Typography from '@mui/material/Typography';
import { useMediaQuery } from 'react-responsive';

const STEPS = ['Open', 'In progress', 'Resolved', 'Closed', 'Archived'];

/** Index of the current step for each status. Blocked sits on "In progress". */
const STEP_INDEX = {
  open: 0,
  in_progress: 1,
  blocked: 1,
  resolved: 2,
  closed: 3,
};

/**
 * Shows where a ticket is in the workflow. Blocked is shown in red on the
 * "In progress" step; archived tickets show every step complete.
 * @param {{status: string, archived?: boolean}} props
 * @returns {JSX.Element}
 */
export default function WorkflowStepper({ status, archived = false }) {
  const isMobile = useMediaQuery({ maxWidth: 600 });
  const activeStep = archived ? STEPS.length : STEP_INDEX[status] ?? 0;

  return (
    <Stepper
      activeStep={activeStep}
      orientation={isMobile ? 'vertical' : 'horizontal'}
      alternativeLabel={!isMobile}
      aria-label="Ticket progress"
    >
      {STEPS.map((label, index) => {
        const isBlocked = status === 'blocked' && index === 1 && !archived;
        return (
          <Step key={label}>
            <StepLabel
              error={isBlocked}
              optional={isBlocked ? <Typography variant="caption" color="error">Blocked</Typography> : null}
            >
              {label}
            </StepLabel>
          </Step>
        );
      })}
    </Stepper>
  );
}

WorkflowStepper.propTypes = {
  status: PropTypes.oneOf(['open', 'in_progress', 'blocked', 'resolved', 'closed']).isRequired,
  archived: PropTypes.bool,
};
