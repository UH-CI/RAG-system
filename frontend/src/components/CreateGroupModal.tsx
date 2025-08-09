import React, { useState, useEffect, useRef } from "react";
import { X, Upload, FileText, ChevronDown, ChevronUp, HelpCircle, Link, Trash2 } from "lucide-react";
import { createCollection, uploadPDFToCollection, uploadFromGoogleDrive, uploadFromWebUrl, extractText, chunkText } from "../services/api";

// Modal component props interface


interface CreateGroupModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

const CreateGroupModal: React.FC<CreateGroupModalProps> = ({ isOpen, onClose, onSuccess }) => {
  // Modal state
  const modalRef = useRef<HTMLDivElement>(null);
  
  // Modal state
  const [loading, setLoading] = useState<boolean>(false);
  
  // Form state
  const [collectionName, setCollectionName] = useState<string>("");
  const [, setCollectionDescription] = useState<string>("");
  const [uploadMethod, setUploadMethod] = useState<'file' | 'drive' | 'web'>('drive');
  
  // File upload state
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [driveLink, setDriveLink] = useState<string>("");
  const [recursive, setRecursive] = useState<boolean>(false);
  const [webUrl, setWebUrl] = useState<string>("");
  
  // Text extraction settings
  const [extractTables, setExtractTables] = useState<boolean>(false);
  const [extractImagesWithText, setExtractImagesWithText] = useState<boolean>(false);
  const [extractImagesWithoutText, setExtractImagesWithoutText] = useState<boolean>(false);
  
  // Chunking settings
  const [chunkingMethod, setChunkingMethod] = useState<'paragraph' | 'fixed' | 'semantic'>('paragraph');
  const [chunkSize, setChunkSize] = useState<number>(1000);
  const [chunkOverlap, setChunkOverlap] = useState<number>(100);
  const [useAI, setUseAI] = useState<boolean>(false);
  const [contextPrompt, setContextPrompt] = useState<string>("");

  // Sections collapsed state
  const [sectionsCollapsed, setSectionsCollapsed] = useState({
    collections: false,
    uploadOptions: false,
    extractionOptions: false,
    chunkingOptions: false
  });

  // Handle outside click to close modal
  useEffect(() => {
    const handleOutsideClick = (event: MouseEvent) => {
      if (modalRef.current && !modalRef.current.contains(event.target as Node)) {
        onClose();
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleOutsideClick);
    }

    return () => {
      document.removeEventListener('mousedown', handleOutsideClick);
    };
  }, [isOpen, onClose]);

  // Initialize modal when opened
  useEffect(() => {
    if (isOpen) {
      // Reset form values when modal opens
      setCollectionName('');
      setCollectionDescription('');
      setUploadMethod('file');
      setSelectedFiles([]);
      setDriveLink('');
      setWebUrl('');
      setRecursive(false);
    }
  }, [isOpen]);

  const toggleSection = (section: keyof typeof sectionsCollapsed) => {
    setSectionsCollapsed(prev => ({
      ...prev,
      [section]: !prev[section]
    }));
  };

  // File selection handler
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const fileList = e.target.files;
    if (!fileList) return;
    
    const newFiles = Array.from(fileList);
    setSelectedFiles(prev => [...prev, ...newFiles]);
  };

  // Remove selected file
  const removeFile = (index: number) => {
    setSelectedFiles(prev => prev.filter((_, i) => i !== index));
  };

  // Form submission handler
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      // First step: Create collection
      const { collection_path } = await createCollection(collectionName);
      
      // Second step: Upload documents based on selected method
      if (uploadMethod === 'file' && selectedFiles.length > 0) {
        await uploadPDFToCollection(selectedFiles, collection_path);
      } else if (uploadMethod === 'drive' && driveLink) {
        await uploadFromGoogleDrive(driveLink, collection_path, recursive);
      } else if (uploadMethod === 'web' && webUrl) {
        await uploadFromWebUrl(webUrl, collection_path);
      }
      
      // Third step: Text extraction
      await extractText(
        collection_path,
        extractTables,
        extractImagesWithText,
        extractImagesWithoutText
      );
      
      // Fourth step: Chunking
      await chunkText(
        collection_path,
        chunkingMethod,
        chunkSize,
        chunkOverlap,
        useAI,
        contextPrompt
      );
      
      onSuccess();
    } catch (error) {
      console.error("Error creating collection or uploading documents:", error);
    } finally {
      setLoading(false);
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 flex items-center justify-center bg-black bg-opacity-50 z-50 overflow-auto py-10">
      <div 
        ref={modalRef}
        className="bg-white rounded-lg shadow-xl w-full max-w-4xl max-h-[90vh] overflow-y-auto relative"
      >
        {/* Modal content will be implemented in the next part */}
        <div className="p-6">
          <div className="flex justify-between items-center border-b pb-4 mb-4">
            <h2 className="text-2xl font-bold">Create Collection</h2>
            <button 
              onClick={onClose}
              className="p-1 rounded-full hover:bg-gray-100"
              aria-label="Close"
            >
              <X size={24} />
            </button>
          </div>
          
          {/* Collection information section */}
          <div className="mb-6">
            <div className="flex justify-between items-center mb-3">
              <h3 className="text-lg font-semibold">Collection Information</h3>
              <button 
                onClick={() => toggleSection('collections')}
                className="flex items-center text-gray-500 hover:text-gray-700"
              >
                {sectionsCollapsed.collections ? <ChevronDown size={20} /> : <ChevronUp size={20} />}
              </button>
            </div>
            
            {!sectionsCollapsed.collections && (
              <div className="space-y-4 animate-fade-in">
                <div className="space-y-2">
                  <label htmlFor="collection-name" className="block text-sm font-medium text-gray-700">
                    Collection Name *
                  </label>
                  <input
                    id="collection-name"
                    type="text"
                    value={collectionName}
                    onChange={(e) => setCollectionName(e.target.value)}
                    placeholder="Enter collection name"
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                    required
                  />
                </div>
                
                {/* <div className="space-y-2">
                  <label htmlFor="collection-desc" className="block text-sm font-medium text-gray-700">
                    Description
                  </label>
                  <textarea
                    id="collection-desc"
                    value={collectionDescription}
                    onChange={(e) => setCollectionDescription(e.target.value)}
                    placeholder="Enter collection description"
                    rows={3}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                </div> */}
              </div>
            )}
          </div>
          
          {/* Upload options section */}
          <div className="mb-6">
            <div className="flex justify-between items-center mb-3">
              <h3 className="text-lg font-semibold">Upload Documents</h3>
              <button 
                onClick={() => toggleSection('uploadOptions')}
                className="flex items-center text-gray-500 hover:text-gray-700"
              >
                {sectionsCollapsed.uploadOptions ? <ChevronDown size={20} /> : <ChevronUp size={20} />}
              </button>
            </div>
            
            {!sectionsCollapsed.uploadOptions && (
              <div className="space-y-4 animate-fade-in">
                <div className="flex space-x-4 mb-4">
                  <button
                    type="button"
                    className={`flex items-center px-4 py-2 rounded-md ${uploadMethod === 'file' ? 'bg-primary-50 text-primary-700 border border-primary-200' : 'bg-white border border-gray-300'}`}
                    onClick={() => setUploadMethod('file')}
                  >
                    <Upload size={18} className="mr-2" />
                    Upload Files
                  </button>
                  
                  <button
                    type="button"
                    className={`flex items-center px-4 py-2 rounded-md ${uploadMethod === 'drive' ? 'bg-primary-50 text-primary-700 border border-primary-200' : 'bg-white border border-gray-300'}`}
                    onClick={() => setUploadMethod('drive')}
                  >
                    <Link size={18} className="mr-2" />
                    Google Drive
                  </button>
                  
                  <button
                    type="button"
                    className={`flex items-center px-4 py-2 rounded-md ${uploadMethod === 'web' ? 'bg-primary-50 text-primary-700 border border-primary-200' : 'bg-white border border-gray-300'}`}
                    onClick={() => setUploadMethod('web')}
                  >
                    <FileText size={18} className="mr-2" />
                    Web URL
                  </button>
                </div>
                
                {/* File upload UI */}
                {uploadMethod === 'file' && (
                  <div className="space-y-4">
                    <div 
                      className="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center hover:border-primary-300 transition-colors cursor-pointer"
                      onClick={() => document.getElementById('file-upload')?.click()}
                    >
                      <Upload size={32} className="mx-auto mb-2 text-gray-400" />
                      <p className="text-sm text-gray-500 mb-1">Drag and drop your files here</p>
                      <p className="text-xs text-gray-400">or click to browse</p>
                      <input 
                        id="file-upload" 
                        type="file" 
                        multiple 
                        accept=".pdf" 
                        className="hidden" 
                        onChange={handleFileSelect} 
                      />
                    </div>
                    
                    {/* Selected files list */}
                    {selectedFiles.length > 0 && (
                      <div className="space-y-2">
                        <h4 className="text-sm font-medium">Selected Files ({selectedFiles.length})</h4>
                        <div className="max-h-40 overflow-y-auto">
                          {selectedFiles.map((file, index) => (
                            <div key={index} className="flex justify-between items-center p-2 bg-gray-50 rounded-md">
                              <div className="flex items-center">
                                <FileText size={16} className="mr-2 text-gray-500" />
                                <span className="text-sm truncate" style={{ maxWidth: '200px' }}>
                                  {file.name}
                                </span>
                                <span className="text-xs text-gray-400 ml-2">
                                  ({(file.size / 1024).toFixed(1)} KB)
                                </span>
                              </div>
                              <button 
                                type="button"
                                onClick={() => removeFile(index)}
                                className="p-1 hover:bg-gray-200 rounded-full"
                              >
                                <Trash2 size={16} className="text-gray-400" />
                              </button>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
                
                {/* Google Drive UI */}
                {uploadMethod === 'drive' && (
                  <div className="space-y-4">
                    <div className="space-y-2">
                      <label htmlFor="drive-link" className="block text-sm font-medium text-gray-700">
                        Google Drive Folder Link
                      </label>
                      <input
                        id="drive-link"
                        type="url"
                        value={driveLink}
                        onChange={(e) => setDriveLink(e.target.value)}
                        placeholder="https://drive.google.com/drive/folders/..."
                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                      />
                    </div>
                    
                    <div className="flex items-center">
                      <input
                        id="recursive-checkbox"
                        type="checkbox"
                        checked={recursive}
                        onChange={(e) => setRecursive(e.target.checked)}
                        className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                      />
                      <label htmlFor="recursive-checkbox" className="ml-2 block text-sm text-gray-700">
                        Process subfolders recursively
                      </label>
                      <div className="group relative ml-2">
                        <HelpCircle size={16} className="text-gray-400 cursor-help" />
                        <div className="hidden group-hover:block absolute left-0 bottom-full mb-2 w-56 p-2 bg-gray-800 text-white text-xs rounded shadow-lg">
                          If enabled, the system will download PDF files from all subfolders within the linked folder.
                        </div>
                      </div>
                    </div>
                  </div>
                )}
                
                {/* Web URL UI */}
                {uploadMethod === 'web' && (
                  <div className="space-y-2">
                    <label htmlFor="web-url" className="block text-sm font-medium text-gray-700">
                      Website URL
                    </label>
                    <input
                      id="web-url"
                      type="url"
                      value={webUrl}
                      onChange={(e) => setWebUrl(e.target.value)}
                      placeholder="https://example.com"
                      className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                    />
                    <p className="text-xs text-gray-500 mt-1">
                      The system will crawl and extract content from the provided URL.
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>
          
          {/* Text extraction settings section */}
          <div className="mb-6">
            <div className="flex justify-between items-center mb-3">
              <h3 className="text-lg font-semibold">Text Extraction Settings</h3>
              <button 
                onClick={() => toggleSection('extractionOptions')}
                className="flex items-center text-gray-500 hover:text-gray-700"
              >
                {sectionsCollapsed.extractionOptions ? <ChevronDown size={20} /> : <ChevronUp size={20} />}
              </button>
            </div>
            
            {!sectionsCollapsed.extractionOptions && (
              <div className="space-y-4 animate-fade-in">
                <div className="p-4 bg-gray-50 rounded-md space-y-3">
                  <div className="flex items-center">
                    <input
                      id="extract-tables"
                      type="checkbox"
                      checked={extractTables}
                      onChange={(e) => setExtractTables(e.target.checked)}
                      className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                    />
                    <label htmlFor="extract-tables" className="ml-2 block text-sm text-gray-700">
                      Extract tables
                    </label>
                  </div>
                  
                  <div className="flex items-center">
                    <input
                      id="extract-images-with-text"
                      type="checkbox"
                      checked={extractImagesWithText}
                      onChange={(e) => setExtractImagesWithText(e.target.checked)}
                      className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                    />
                    <label htmlFor="extract-images-with-text" className="ml-2 block text-sm text-gray-700">
                      Extract images with text
                    </label>
                  </div>
                  
                  <div className="flex items-center">
                    <input
                      id="extract-images-without-text"
                      type="checkbox"
                      checked={extractImagesWithoutText}
                      onChange={(e) => setExtractImagesWithoutText(e.target.checked)}
                      className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                    />
                    <label htmlFor="extract-images-without-text" className="ml-2 block text-sm text-gray-700">
                      Extract images without text
                    </label>
                  </div>
                </div>
              </div>
            )}
          </div>
          
          {/* Chunking settings section */}
          <div className="mb-6">
            <div className="flex justify-between items-center mb-3">
              <h3 className="text-lg font-semibold">Chunking Settings</h3>
              <button 
                onClick={() => toggleSection('chunkingOptions')}
                className="flex items-center text-gray-500 hover:text-gray-700"
              >
                {sectionsCollapsed.chunkingOptions ? <ChevronDown size={20} /> : <ChevronUp size={20} />}
              </button>
            </div>
            
            {!sectionsCollapsed.chunkingOptions && (
              <div className="space-y-4 animate-fade-in">
                <div className="space-y-2">
                  <label className="block text-sm font-medium text-gray-700">
                    Chunking Method
                  </label>
                  <div className="flex space-x-4">
                    <div className="flex items-center">
                      <input
                        id="method-paragraph"
                        type="radio"
                        checked={chunkingMethod === 'paragraph'}
                        onChange={() => setChunkingMethod('paragraph')}
                        className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300"
                      />
                      <label htmlFor="method-paragraph" className="ml-2 block text-sm text-gray-700">
                        Paragraph
                      </label>
                    </div>
                    <div className="flex items-center">
                      <input
                        id="method-fixed"
                        type="radio"
                        checked={chunkingMethod === 'fixed'}
                        onChange={() => setChunkingMethod('fixed')}
                        className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300"
                      />
                      <label htmlFor="method-fixed" className="ml-2 block text-sm text-gray-700">
                        Fixed Size
                      </label>
                    </div>
                    <div className="flex items-center">
                      <input
                        id="method-semantic"
                        type="radio"
                        checked={chunkingMethod === 'semantic'}
                        onChange={() => setChunkingMethod('semantic')}
                        className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300"
                      />
                      <label htmlFor="method-semantic" className="ml-2 block text-sm text-gray-700">
                        Semantic
                      </label>
                    </div>
                  </div>
                </div>
                
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <label htmlFor="chunk-size" className="block text-sm font-medium text-gray-700">
                      Chunk Size (characters)
                    </label>
                    <input
                      id="chunk-size"
                      type="number"
                      value={chunkSize}
                      onChange={(e) => setChunkSize(parseInt(e.target.value) || 0)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                      min="100"
                      max="10000"
                    />
                  </div>
                  
                  <div className="space-y-2">
                    <label htmlFor="chunk-overlap" className="block text-sm font-medium text-gray-700">
                      Chunk Overlap (characters)
                    </label>
                    <input
                      id="chunk-overlap"
                      type="number"
                      value={chunkOverlap}
                      onChange={(e) => setChunkOverlap(parseInt(e.target.value) || 0)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                      min="0"
                      max={chunkSize - 1}
                    />
                  </div>
                </div>
                
                <div className="flex items-center mb-2">
                  <input
                    id="use-ai"
                    type="checkbox"
                    checked={useAI}
                    onChange={(e) => setUseAI(e.target.checked)}
                    className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                  />
                  <label htmlFor="use-ai" className="ml-2 block text-sm text-gray-700">
                    Use AI for context enrichment
                  </label>
                </div>
                
                {useAI && (
                  <div className="space-y-2">
                    <label htmlFor="context-prompt" className="block text-sm font-medium text-gray-700">
                      Context Prompt
                    </label>
                    <textarea
                      id="context-prompt"
                      value={contextPrompt}
                      onChange={(e) => setContextPrompt(e.target.value)}
                      placeholder="Enter a prompt for the AI to generate additional context for each chunk..."
                      rows={3}
                      className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                    />
                  </div>
                )}
              </div>
            )}
          </div>
          
          <div className="flex justify-end mt-6 pt-4 border-t">
            <button 
              onClick={onClose}
              className="px-4 py-2 mr-2 border border-gray-300 rounded-md hover:bg-gray-50"
            >
              Cancel
            </button>
            <button 
              onClick={handleSubmit}
              className="px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700 flex items-center"
              disabled={loading}
            >
              {loading ? 'Processing...' : 'Create Collection'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CreateGroupModal;