import { createAsyncThunk, createSlice } from '@reduxjs/toolkit'
import { api } from '../lib/api'

export const fetchProfile = createAsyncThunk('profile/fetch', () => api('/api/me'))
export const saveProfile = createAsyncThunk('profile/save', async (body, { rejectWithValue }) => {
  try { return await api('/api/me', { method: 'PUT', body }) } catch (e) { return rejectWithValue(e.message) }
})

const slice = createSlice({
  name: 'profile',
  // status: idle | loading | ready | missing | error
  initialState: { status: 'idle', profile: null, suggested: {}, editing: false, saving: false, error: null },
  reducers: {
    startEditing: (s) => { s.editing = true; s.error = null },
    stopEditing: (s) => { s.editing = false },
  },
  extraReducers: (b) => {
    b.addCase(fetchProfile.pending, (s) => { s.status = 'loading' })
      .addCase(fetchProfile.fulfilled, (s, a) => {
        s.profile = a.payload.profile
        s.suggested = a.payload.suggested || {}
        s.status = a.payload.profile ? 'ready' : 'missing'
      })
      .addCase(fetchProfile.rejected, (s, a) => { s.status = 'error'; s.error = a.error.message })
      .addCase(saveProfile.pending, (s) => { s.saving = true; s.error = null })
      .addCase(saveProfile.fulfilled, (s, a) => { s.saving = false; s.profile = a.payload.profile; s.status = 'ready'; s.editing = false })
      .addCase(saveProfile.rejected, (s, a) => { s.saving = false; s.error = a.payload || 'Could not save. Try again.' })
  },
})

export const { startEditing, stopEditing } = slice.actions
export default slice.reducer
