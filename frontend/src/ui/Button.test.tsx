import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Button } from '@/ui/Button';

describe('Button', () => {
  it('renders children', () => {
    render(<Button>Click me</Button>);
    expect(screen.getByRole('button', { name: 'Click me' })).toBeInTheDocument();
  });

  it('is disabled when the disabled prop is true', () => {
    render(<Button disabled>Save</Button>);
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('is disabled when loading is true', () => {
    render(<Button loading>Save</Button>);
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('calls onClick when clicked', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Go</Button>);
    await user.click(screen.getByRole('button'));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('does not fire onClick when the button is disabled', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(
      <Button disabled onClick={onClick}>
        Go
      </Button>,
    );
    await user.click(screen.getByRole('button'));
    expect(onClick).not.toHaveBeenCalled();
  });

  it('renders each variant without crashing', () => {
    const variants = ['primary', 'secondary', 'destructive', 'ghost'] as const;
    for (const variant of variants) {
      const { unmount } = render(<Button variant={variant}>Label</Button>);
      expect(screen.getByRole('button')).toBeInTheDocument();
      unmount();
    }
  });

  it('renders sm and md sizes without crashing', () => {
    const sizes = ['sm', 'md'] as const;
    for (const size of sizes) {
      const { unmount } = render(<Button size={size}>Label</Button>);
      expect(screen.getByRole('button')).toBeInTheDocument();
      unmount();
    }
  });
});
