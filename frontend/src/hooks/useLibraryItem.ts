import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import type { components } from '@shared/types'

type LibraryItem = components['schemas']['LibraryItemRead']
type LaunchProfile = components['schemas']['ProfileRead']
type Platform = components['schemas']['PlatformRead']
type User = components['schemas']['UserRead']
type LaunchHistory = components['schemas']['LaunchHistoryRead']

export function useLibraryItem(slug: string | undefined, isAdminOrOwner: boolean) {
  const { data: item, isLoading: itemLoading } = useQuery<LibraryItem>({
    queryKey: ['library', 'by-slug', slug],
    queryFn: () => apiFetch<LibraryItem>(`/api/v1/library/by-slug/${slug}`),
    enabled: !!slug,
  })

  const { data: profiles = [] } = useQuery<LaunchProfile[]>({
    queryKey: ['profiles'],
    queryFn: () => apiFetch<LaunchProfile[]>('/api/v1/profiles'),
  })

  const { data: platforms = [] } = useQuery<Platform[]>({
    queryKey: ['platforms'],
    queryFn: () => apiFetch<Platform[]>('/api/v1/platforms'),
  })

  const { data: users = [] } = useQuery<User[]>({
    queryKey: ['users'],
    queryFn: () => apiFetch<User[]>('/api/v1/users'),
    enabled: isAdminOrOwner,
  })

  const { data: restrictionsData, refetch: refetchRestrictions } = useQuery<{
    restricted_user_ids: number[]
  }>({
    queryKey: ['restrictions', item?.id],
    queryFn: () =>
      apiFetch<{ restricted_user_ids: number[] }>(`/api/v1/library/${item!.id}/restrictions`),
    enabled: isAdminOrOwner && !!item,
  })

  const { data: launchHistory = [] } = useQuery<LaunchHistory[]>({
    queryKey: ['launches', item?.id],
    queryFn: () => apiFetch<LaunchHistory[]>(`/api/v1/library/${item!.id}/launches`),
    enabled: !!item,
  })

  return {
    item,
    itemLoading,
    profiles,
    platforms,
    users,
    restrictionsData,
    refetchRestrictions,
    launchHistory,
  }
}
