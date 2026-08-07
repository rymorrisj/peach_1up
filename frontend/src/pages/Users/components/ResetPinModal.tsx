import { Button, FormField, Input, Modal } from '@/ui';
import type { components } from '@shared/types';

type User = components['schemas']['UserItemRead'];

export type ResetPinTarget = {
  user: User;
  pin: string;
  error: string | null;
  submitting: boolean;
};

interface ResetPinModalProps {
  target: ResetPinTarget;
  onChangePin: (pin: string) => void;
  onSubmit: () => void;
  onClose: () => void;
}

export function ResetPinModal({ target, onChangePin, onSubmit, onClose }: ResetPinModalProps) {
  return (
    <Modal
      open
      title={`Reset PIN, ${target.user.name}`}
      onClose={onClose}
      busy={target.submitting}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={target.submitting}>
            Cancel
          </Button>
          <Button onClick={onSubmit} loading={target.submitting}>
            Set PIN
          </Button>
        </>
      }
    >
      <FormField
        label="New PIN"
        htmlFor="reset-pin"
        hint="4–6 digits."
        error={target.error ?? undefined}
      >
        <Input
          id="reset-pin"
          type="password"
          inputMode="numeric"
          maxLength={6}
          autoFocus
          value={target.pin}
          onChange={(e) => onChangePin(e.target.value.replace(/\D/g, ''))}
          placeholder="••••"
          hasError={!!target.error}
          className="text-center tracking-[0.5em] text-lg"
        />
      </FormField>
    </Modal>
  );
}
