import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/helpers";
import Step4Profile from "./Step4Profile";
import * as client from "@/api/client";

describe("Step4Profile", () => {
  it("renders the Finish Setup button", () => {
    renderWithProviders(<Step4Profile />);
    expect(
      screen.getByRole("button", { name: /finish setup/i }),
    ).toBeInTheDocument();
  });

  it("calls complete-first-run on submit", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "apiFetch").mockResolvedValue({ success: true } as never);

    renderWithProviders(<Step4Profile />);
    await user.click(screen.getByRole("button", { name: /finish setup/i }));

    await waitFor(() => {
      expect(client.apiFetch).toHaveBeenCalledWith(
        "/api/v1/settings/complete-first-run",
        expect.objectContaining({ method: "POST" }),
      );
    });
  });

  it("shows inline error when complete-first-run fails", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "apiFetch").mockRejectedValue(
      Object.assign(new Error(), { detail: "Setup failed." }),
    );

    renderWithProviders(<Step4Profile />);
    await user.click(screen.getByRole("button", { name: /finish setup/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
  });
});
