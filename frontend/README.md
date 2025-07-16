# UH Manoa RAG System - Frontend

A modern React + TypeScript frontend for the University of Hawaii at Manoa RAG (Retrieval-Augmented Generation) system. This application provides an intuitive interface for searching and asking questions about university courses, programs, and academic pathways.

## 🚀 Features

- **Semantic Search**: Find relevant courses, programs, and pathways using natural language queries
- **AI-Powered Q&A**: Ask questions and get intelligent answers with source citations
- **Multi-Collection Support**: Search across different data collections (courses, programs, pathways)
- **Modern UI**: Clean, responsive design built with Tailwind CSS
- **Real-time Results**: Fast search with loading states and error handling
- **Copy to Clipboard**: Easy sharing of search results and answers
- **Expandable Results**: Detailed view of search results with metadata

## 🛠 Tech Stack

- **React 18** - Modern React with hooks and functional components
- **TypeScript** - Type-safe development
- **Vite** - Fast build tool and development server
- **Tailwind CSS** - Utility-first CSS framework
- **Lucide React** - Beautiful icons
- **Axios** - HTTP client for API communication
- **Headless UI** - Accessible UI components

## 📋 Prerequisites

- Node.js 18.x or higher
- npm or yarn package manager
- RAG API server running (see backend setup)

## 🔧 Installation

1. **Clone the repository** (if not already done):
   ```bash
   git clone <repository-url>
   cd RAG-system/frontend
   ```

2. **Install dependencies**:
   ```bash
   npm install
   ```

3. **Configure environment**:
   Create a `.env` file in the frontend directory:
   ```env
   VITE_API_BASE_URL=http://localhost:8200
   VITE_ENV=development
   ```

4. **Start the development server**:
   ```bash
   npm run dev
   ```

5. **Open your browser**:
   Navigate to `http://localhost:3000`

## 🚀 Available Scripts

- `npm run dev` - Start development server on port 3000
- `npm run build` - Build for production
- `npm run preview` - Preview production build
- `npm run lint` - Run ESLint
- `npm run type-check` - Check TypeScript types

## 🔗 API Integration

The frontend communicates with the RAG API backend running on port 8200. Make sure the backend is running before starting the frontend.

### API Endpoints Used:
- `GET /search` - Search documents in collections
- `POST /ask` - Ask questions and get AI answers
- `GET /collections` - Get available collections
- `GET /collections/{id}/stats` - Get collection statistics

## 🎨 UI Components

### SearchInterface
- Search type toggle (Search vs Ask AI)
- Query input with examples
- Advanced options (collection selection, max results)
- Loading states

### ResultDisplay
- Search results with metadata badges
- Expandable content view
- Copy to clipboard functionality
- Syntax highlighting for search terms
- AI answer display with sources

## 🔍 Usage Examples

### Semantic Search
- "computer science courses"
- "mathematics prerequisites"
- "engineering programs"

### AI Questions
- "What are the requirements for a CS degree?"
- "How many credits do I need to graduate?"
- "What math courses are required for engineering?"

## 🚦 Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `VITE_API_BASE_URL` | Backend API URL | `http://localhost:8200` |
| `VITE_ENV` | Environment | `development` |

## 📱 Responsive Design

The application is fully responsive and works on:
- Desktop (1024px+)
- Tablet (768px - 1023px)
- Mobile (320px - 767px)

## 🎯 Collections

The system supports three main collections:

1. **Courses** 📚 - University course catalog
2. **Programs** 🎓 - Academic programs and degrees  
3. **Pathways** 🛤️ - Degree pathways and requirements

## 🔧 Development

### Project Structure
```
frontend/
├── src/
│   ├── components/
│   │   ├── SearchInterface.tsx
│   │   └── ResultDisplay.tsx
│   ├── services/
│   │   └── api.ts
│   ├── types.ts
│   ├── App.tsx
│   └── main.tsx
├── public/
├── tailwind.config.js
├── postcss.config.js
└── vite.config.ts
```

### Adding New Features

1. Create new components in `src/components/`
2. Add types to `src/types.ts`
3. Update API service in `src/services/api.ts`
4. Add new routes to main App component

## 🐛 Troubleshooting

### Common Issues

1. **API Connection Error**
   - Ensure backend is running on port 8200
   - Check CORS settings on backend
   - Verify VITE_API_BASE_URL in .env

2. **Build Errors**
   - Run `npm run type-check` to verify TypeScript
   - Ensure all dependencies are installed
   - Clear node_modules and reinstall if needed

3. **Styling Issues**
   - Rebuild Tailwind styles with `npm run build`
   - Check Tailwind config includes all source files

## 📈 Performance

- Code splitting with dynamic imports
- Optimized bundle size with Vite
- Lazy loading of search results
- Debounced search input (coming soon)

## 🔮 Future Enhancements

- [ ] Search history and favorites
- [ ] Advanced filters and sorting
- [ ] Pagination for large result sets
- [ ] Dark mode support
- [ ] Export search results
- [ ] Keyboard shortcuts
- [ ] Search analytics dashboard

## 📄 License

This project is part of the UH Manoa RAG System.
