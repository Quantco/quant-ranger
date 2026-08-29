import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router/dom'

import { TooltipProvider } from './components/ui/tooltip'
import { router } from './Site'
import './styles.css'

const root = document.getElementById('root')
if (root == null) throw new Error('Dashboard root element is missing')

createRoot(root).render(
  <StrictMode>
    <TooltipProvider>
      <RouterProvider router={router} />
    </TooltipProvider>
  </StrictMode>
)
