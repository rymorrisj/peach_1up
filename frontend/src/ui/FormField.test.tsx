import { render, screen } from '@testing-library/react';
import { FormField } from '@/ui/FormField';

describe('FormField', () => {
  it('renders the label and children', () => {
    render(
      <FormField label="Username">
        <input id="u" />
      </FormField>,
    );
    expect(screen.getByText('Username')).toBeInTheDocument();
    expect(screen.getByRole('textbox')).toBeInTheDocument();
  });

  it('associates the label with the child input via htmlFor', () => {
    render(
      <FormField label="Email" htmlFor="email">
        <input id="email" />
      </FormField>,
    );
    expect(screen.getByLabelText('Email')).toBeInTheDocument();
  });

  it('renders the required asterisk when required is true', () => {
    render(
      <FormField label="Name" required>
        <input />
      </FormField>,
    );
    expect(screen.getByText('*')).toBeInTheDocument();
  });

  it('does not render the asterisk when required is not set', () => {
    render(
      <FormField label="Name">
        <input />
      </FormField>,
    );
    expect(screen.queryByText('*')).not.toBeInTheDocument();
  });

  it('shows hint text when no error is present', () => {
    render(
      <FormField label="Bio" hint="Max 200 characters">
        <textarea />
      </FormField>,
    );
    expect(screen.getByText('Max 200 characters')).toBeInTheDocument();
  });

  it('shows the error with role=alert and hides the hint when error is provided', () => {
    render(
      <FormField label="Bio" hint="Max 200 characters" error="Value is too long">
        <textarea />
      </FormField>,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Value is too long');
    expect(screen.queryByText('Max 200 characters')).not.toBeInTheDocument();
  });
});
