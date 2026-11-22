import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { renderWithProviders } from '@/test/helpers';
import Sidebar from './Sidebar';

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{`${location.pathname}${location.search}`}</div>;
}

function renderSidebar() {
  return renderWithProviders(
    <MemoryRouter initialEntries={['/software']}>
      <Sidebar />
      <Routes>
        <Route path="*" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
  );
}

function listNamed(name: string) {
  return screen.getByRole('list', { name });
}

describe('Sidebar Platforms list', () => {
  it('shows one Platforms heading with PC and Console subgroups, no Eras or Consoles groups', () => {
    renderSidebar();

    expect(screen.getByText('Platforms')).toBeInTheDocument();
    expect(listNamed('PC')).toBeInTheDocument();
    expect(listNamed('Console')).toBeInTheDocument();
    expect(screen.queryByText('Eras')).not.toBeInTheDocument();
    expect(screen.queryByText('Consoles')).not.toBeInTheDocument();
  });

  it('lists the PC platforms under PC', () => {
    renderSidebar();
    const pc = listNamed('PC');

    for (const label of ['DOS', 'Windows 95', 'Windows 98', 'Windows XP']) {
      expect(within(pc).getByRole('button', { name: new RegExp(label) })).toBeInTheDocument();
    }
    expect(within(pc).queryByRole('button', { name: /PlayStation/ })).not.toBeInTheDocument();
  });

  it('lists every console platform under Console, including PS3 and Xbox 360', () => {
    renderSidebar();
    const consoles = listNamed('Console');

    for (const label of [
      'PlayStation 1',
      'PlayStation 3',
      'Xbox 360',
      'Nintendo 64',
      'Dreamcast',
    ]) {
      expect(within(consoles).getByRole('button', { name: new RegExp(label) })).toBeInTheDocument();
    }
    expect(within(consoles).queryByRole('button', { name: /Windows/ })).not.toBeInTheDocument();
  });

  it('links a platform to the games list filtered by ?platform=', async () => {
    const user = userEvent.setup();
    renderSidebar();

    await user.click(within(listNamed('Console')).getByRole('button', { name: /Xbox 360/ }));

    expect(screen.getByTestId('location')).toHaveTextContent('/software/games?platform=xbox360');
  });
});
