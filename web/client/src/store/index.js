import { configureStore } from '@reduxjs/toolkit'
import profile from './profileSlice'
import chat from './chatSlice'

export const store = configureStore({ reducer: { profile, chat } })
