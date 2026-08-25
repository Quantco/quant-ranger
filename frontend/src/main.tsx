import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import Site from './Site'
import './styles.css'

const root = document.getElementById('root')
if (root == null) throw new Error('Dashboard root element is missing')

createRoot(root).render(
  <StrictMode>
    <Site />
  </StrictMode>
)
