"use client"

import type React from "react"
import { useState, useRef } from "react"
import { X, Info, Upload, FileText, Trash2, Eye, AlertTriangle } from "lucide-react"
import { useFlowStore } from "../../store/flowStore"
import type { Node, Edge } from "@xyflow/react"

// Helper function to find the email node that comes before a conditional node
const findPrecedingEmailNode = (conditionalNodeId: string, nodes: Node[], edges: Edge[]): Node | null => {
  // Find edges that connect to this conditional node
  const incomingEdges = edges.filter(edge => edge.target === conditionalNodeId)
  
  for (const edge of incomingEdges) {
    const sourceNode = nodes.find(node => node.id === edge.source)
    if (sourceNode && sourceNode.type === "sendEmail") {
      return sourceNode
    }
    
    // If the source is not an email node, recursively check its predecessors
    if (sourceNode) {
      const precedingEmail = findPrecedingEmailNode(sourceNode.id, nodes, edges)
      if (precedingEmail) {
        return precedingEmail
      }
    }
  }
  
  return null
}

export const PropertyPanel: React.FC = () => {
  const { nodes, edges, selectedNode, setSelectedNode, updateNode, contactFile, setContactFile } = useFlowStore()
  const [dragActive, setDragActive] = useState(false)
  const [showPreview, setShowPreview] = useState(false)
  const [previewData, setPreviewData] = useState<{ name: string[]; email: string[] } | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const selectedNodeData = nodes.find((node) => node.id === selectedNode)

  // Debug logging
  console.log("Selected node:", selectedNode)
  console.log("Selected node data:", selectedNodeData)
  console.log("Node type:", selectedNodeData?.type)

  if (!selectedNode || !selectedNodeData || !selectedNodeData.data) return null

  const handleClose = () => {
    setSelectedNode(null)
  }

  const parseCSVPreview = async (file: File) => {
    try {
      const text = await file.text()
      const lines = text
        .split("\n")
        .filter((line) => line.trim() !== "")
        .slice(0, 6) // First 5 rows + header

      if (lines.length === 0) return { name: [], email: [] }

      // Get headers and convert to lowercase for comparison
      const headers = lines[0].split(",").map((h) => h.trim().replace(/"/g, "").toLowerCase())

      // Find name and email column indices - simplified to only look for "name" and "email"
      const nameIndex = headers.findIndex((h) => h === "name")
      const emailIndex = headers.findIndex((h) => h === "email" || h.includes("email") || h.includes("mail"))

      const names: string[] = []
      const emails: string[] = []

      // Process data rows (skip header row)
      for (let i = 1; i < lines.length; i++) {
        const values = lines[i].split(",").map((v) => v.trim().replace(/"/g, ""))

        // Handle name column
        if (nameIndex >= 0 && values[nameIndex] && values[nameIndex].trim() !== "") {
          names.push(values[nameIndex].trim())
        } else {
          names.push(`Contact ${i}`)
        }

        // Handle email column
        if (emailIndex >= 0 && values[emailIndex] && values[emailIndex].trim() !== "") {
          emails.push(values[emailIndex].trim())
        } else {
          emails.push("")
        }
      }

      return { name: names, email: emails }
    } catch (error) {
      console.error("Error parsing CSV:", error)
      return { name: [], email: [] }
    }
  }

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true)
    } else if (e.type === "dragleave") {
      setDragActive(false)
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFiles(e.dataTransfer.files)
    }
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault()
    if (e.target.files && e.target.files[0]) {
      handleFiles(e.target.files)
    }
  }

  const handleFiles = async (files: FileList) => {
    const file = files[0]
    const allowedTypes = [
      "text/csv",
      "application/vnd.ms-excel",
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ]

    if (
      allowedTypes.includes(file.type) ||
      file.name.endsWith(".csv") ||
      file.name.endsWith(".xls") ||
      file.name.endsWith(".xlsx")
    ) {
      setContactFile(file)

      // Generate preview for CSV files
      if (file.name.endsWith(".csv") || file.type === "text/csv") {
        const preview = await parseCSVPreview(file)
        setPreviewData(preview)
      }
    } else {
      alert("Please upload a CSV, XLS, or XLSX file")
    }
  }

  const removeFile = () => {
    setContactFile(null)
    setPreviewData(null)
    setShowPreview(false)
  }

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return "0 Bytes"
    const k = 1024
    const sizes = ["Bytes", "KB", "MB", "GB"]
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return Number.parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i]
  }

  const renderNodeProperties = () => {
    switch (selectedNodeData.type) {
      case "start":
        return (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Contact List</label>

              {contactFile ? (
                <div className="border border-green-300 rounded-lg p-3 bg-green-50">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center space-x-2">
                      <FileText className="w-4 h-4 text-green-600" />
                      <div>
                        <p className="text-sm font-medium text-green-900">{contactFile.name}</p>
                        <p className="text-xs text-green-600">{formatFileSize(contactFile.size)}</p>
                      </div>
                    </div>
                    <div className="flex items-center space-x-1">
                      {previewData && (
                        <button
                          onClick={() => setShowPreview(!showPreview)}
                          className="p-1 hover:bg-green-200 rounded text-green-600"
                          title="Preview data"
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                      )}
                      <button onClick={removeFile} className="p-1 hover:bg-red-100 rounded text-red-600">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>

                  {showPreview && previewData && (
                    <div className="mt-3 p-2 bg-white rounded border">
                      <h4 className="text-xs font-medium text-gray-700 mb-2">Preview (first 5 rows):</h4>
                      <div className="text-xs space-y-1">
                        <div className="flex justify-between font-medium text-gray-800 border-b pb-1">
                          <span>Name</span>
                          <span>Email</span>
                        </div>
                        {previewData.name.slice(0, 5).map((name, index) => (
                          <div key={index} className="flex justify-between">
                            <span className="text-gray-600 truncate max-w-[120px]" title={name}>
                              {name}
                            </span>
                            <span className="text-blue-600 truncate max-w-[120px]" title={previewData.email[index]}>
                              {previewData.email[index] || "N/A"}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div
                  className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
                    dragActive
                      ? "border-green-400 bg-green-50"
                      : "border-gray-300 hover:border-green-400 hover:bg-green-50"
                  }`}
                  onDragEnter={handleDrag}
                  onDragLeave={handleDrag}
                  onDragOver={handleDrag}
                  onDrop={handleDrop}
                  onClick={() => fileInputRef.current?.click()}
                >
                  <Upload className="w-8 h-8 text-gray-400 mx-auto mb-2" />
                  <p className="text-sm text-gray-600 mb-1">Drop your contact list here, or click to browse</p>
                  <p className="text-xs text-gray-500">Supports CSV, XLS, XLSX files</p>
                  <p className="text-xs text-gray-400 mt-2">CSV should have exactly two columns: "name" and "email"</p>
                </div>
              )}

              <input
                ref={fileInputRef}
                type="file"
                accept=".csv,.xls,.xlsx"
                onChange={handleChange}
                className="hidden"
              />
            </div>

            <div className="p-3 bg-green-50 rounded-lg">
              <div className="flex items-start space-x-2">
                <Info className="w-4 h-4 text-green-600 mt-0.5" />
                <div>
                  <p className="text-sm text-green-800 font-medium">Contact List Requirements</p>
                  <p className="text-xs text-green-600 mt-1">
                    Upload a CSV file containing your contact information to begin the campaign.
                  </p>
                </div>
              </div>
            </div>
          </div>
        )

      case "sendEmail":
        return (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Subject</label>
              <input
                type="text"
                value={selectedNodeData.data?.config?.subject || ""}
                onChange={(e) =>
                  updateNode(selectedNode, {
                    config: { ...selectedNodeData.data?.config, subject: e.target.value },
                  })
                }
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500"
                placeholder="Enter email subject"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Body</label>
              <textarea
                value={selectedNodeData.data?.config?.body || ""}
                onChange={(e) =>
                  updateNode(selectedNode, {
                    config: { ...selectedNodeData.data?.config, body: e.target.value },
                  })
                }
                rows={8}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500 resize-none"
                placeholder="Enter email body content"
              />
            </div>
            
            {/* Link Management Section */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Links</label>
              <div className="space-y-2">
                {(selectedNodeData.data?.config?.links || []).map((link: any, index: number) => (
                  <div key={index} className="flex space-x-2 items-center">
                    <input
                      type="text"
                      value={link.text || ""}
                      onChange={(e) => {
                        const newLinks = [...(selectedNodeData.data?.config?.links || [])]
                        newLinks[index] = { ...newLinks[index], text: e.target.value }
                        updateNode(selectedNode, {
                          config: { ...selectedNodeData.data?.config, links: newLinks },
                        })
                      }}
                      placeholder="Link text"
                      className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500 text-sm"
                    />
                    <input
                      type="url"
                      value={link.url || ""}
                      onChange={(e) => {
                        const newLinks = [...(selectedNodeData.data?.config?.links || [])]
                        newLinks[index] = { ...newLinks[index], url: e.target.value }
                        updateNode(selectedNode, {
                          config: { ...selectedNodeData.data?.config, links: newLinks },
                        })
                      }}
                      placeholder="https://example.com"
                      className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500 text-sm"
                    />
                    <button
                      onClick={() => {
                        const newLinks = [...(selectedNodeData.data?.config?.links || [])]
                        newLinks.splice(index, 1)
                        updateNode(selectedNode, {
                          config: { ...selectedNodeData.data?.config, links: newLinks },
                        })
                      }}
                      className="p-2 text-red-500 hover:text-red-700"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))}
                <button
                  onClick={() => {
                    const newLinks = [...(selectedNodeData.data?.config?.links || []), { text: "", url: "" }]
                    updateNode(selectedNode, {
                      config: { ...selectedNodeData.data?.config, links: newLinks },
                    })
                  }}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-600 hover:bg-gray-50 text-sm"
                >
                  + Add Link
                </button>
              </div>
              <p className="text-xs text-gray-500 mt-1">
                Add links to your email. These will be tracked for click events.
              </p>
            </div>
            
            <div className="p-3 bg-blue-50 rounded-lg">
              <div className="flex items-start space-x-2">
                <Info className="w-4 h-4 text-blue-600 mt-0.5" />
                <div>
                  <p className="text-sm text-blue-800 font-medium">Email Configuration</p>
                  <p className="text-xs text-blue-600 mt-1">
                    Configure the subject, body content, and links for your email campaign. Links will be automatically tracked for click events.
                  </p>
                </div>
              </div>
            </div>
          </div>
        )

      case "wait":
        return (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Wait Duration</label>
              <div className="flex space-x-2">
                <input
                  type="number"
                  min="1"
                  max="365"
                  value={selectedNodeData.data?.config?.waitDuration || 1}
                  onChange={(e) =>
                    updateNode(selectedNode, {
                      config: { ...selectedNodeData.data?.config, waitDuration: Number.parseInt(e.target.value) || 1 },
                    })
                  }
                  className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-yellow-500"
                />
                <select
                  value={selectedNodeData.data?.config?.waitUnit || "days"}
                  onChange={(e) =>
                    updateNode(selectedNode, {
                      config: { ...selectedNodeData.data?.config, waitUnit: e.target.value },
                    })
                  }
                  className="px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-yellow-500"
                >
                  <option value="minutes">Minutes</option>
                  <option value="hours">Hours</option>
                  <option value="days">Days</option>
                </select>
              </div>
            </div>
            <div className="p-3 bg-yellow-50 rounded-lg">
              <div className="flex items-start space-x-2">
                <Info className="w-4 h-4 text-yellow-600 mt-0.5" />
                <div>
                  <p className="text-sm text-yellow-800 font-medium">Timing Note</p>
                  <p className="text-xs text-yellow-600 mt-1">
                    Users will wait for the specified duration before proceeding to the next step.
                  </p>
                </div>
              </div>
            </div>
          </div>
        )

      case "condition":
        return (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Condition Type</label>
              <select
                value={selectedNodeData.data?.config?.conditionType || "open"}
                onChange={(e) => {
                  console.log("Condition type changed to:", e.target.value)
                  updateNode(selectedNode, {
                    config: { ...selectedNodeData.data?.config, conditionType: e.target.value },
                  })
                }}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-purple-500"
              >
                <option value="open">Email Opened</option>
                <option value="click">Link Clicked</option>
              </select>
              <p className="text-xs text-gray-500 mt-1">
                Current value: {selectedNodeData.data?.config?.conditionType || "open"}
              </p>
            </div>
            
            {/* Auto-detect email node and show status */}
            {(() => {
              // Find the email node that comes before this conditional node
              const emailNode = findPrecedingEmailNode(selectedNode, nodes, edges)
              
              if (!emailNode) {
                return (
                  <div className="mt-2 p-2 bg-red-50 rounded-lg border border-red-200">
                    <div className="flex items-start space-x-2">
                      <AlertTriangle className="w-4 h-4 text-red-600 mt-0.5" />
                      <div>
                        <p className="text-xs text-red-800 font-medium">No Email Node Found</p>
                        <p className="text-xs text-red-700 mt-1">
                          This condition requires an email node to come before it in the flow. Add an email node above this condition.
                        </p>
                      </div>
                    </div>
                  </div>
                )
              }
              
              const emailLinks = emailNode.data?.config?.links || []
              const hasLinks = emailLinks.length > 0
              
              return (
                <div className="mt-2 p-2 bg-green-50 rounded-lg border border-green-200">
                  <div className="flex items-start space-x-2">
                    <Info className="w-4 h-4 text-green-600 mt-0.5" />
                    <div>
                      <p className="text-xs text-green-800 font-medium">Tracking Email: {emailNode.data?.label}</p>
                      <p className="text-xs text-green-700 mt-1">
                        {selectedNodeData.data?.config?.conditionType === "open" 
                          ? "This condition will track email opens from the email above."
                          : hasLinks 
                            ? `This condition will track link clicks from the email above. Found ${emailLinks.length} link(s).`
                            : "This condition will track link clicks, but the email above has no links."
                        }
                      </p>
                      {selectedNodeData.data?.config?.conditionType === "click" && !hasLinks && (
                        <div className="mt-2 p-2 bg-yellow-50 rounded-lg border border-yellow-200">
                          <div className="flex items-start space-x-2">
                            <AlertTriangle className="w-4 h-4 text-yellow-600 mt-0.5" />
                            <div>
                              <p className="text-xs text-yellow-800 font-medium">No Links Available</p>
                              <p className="text-xs text-yellow-700 mt-1">
                                The email node above doesn't have any links. Add links to the email node to track click events.
                              </p>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )
            })()}
            
            <div className="p-3 bg-purple-50 rounded-lg">
              <div className="flex items-start space-x-2">
                <Info className="w-4 h-4 text-purple-600 mt-0.5" />
                <div>
                  <p className="text-sm text-purple-800 font-medium">Branching Logic</p>
                  <p className="text-xs text-purple-600 mt-1">
                    {selectedNodeData.data?.config?.conditionType === "open" 
                      ? "This condition will track if the email node above was opened by the recipient. Connect the 'Yes' output to the path for users who opened the email, and 'No' for those who didn't. The 'No' path must start with a wait node."
                      : selectedNodeData.data?.config?.conditionType === "click"
                      ? "This condition will track if any link was clicked in the email above. Connect the 'Yes' output to the path for users who clicked a link, and 'No' for those who didn't. The 'No' path must start with a wait node."
                      : "Connect the 'Yes' output to the path for users who meet the condition, and 'No' for those who don't. The 'No' path must start with a wait node."
                    }
                  </p>
                </div>
              </div>
            </div>
          </div>
        )



      case "end":
        return (
          <div className="space-y-4">
            <div className="p-3 bg-red-50 rounded-lg">
              <div className="flex items-start space-x-2">
                <Info className="w-4 h-4 text-red-600 mt-0.5" />
                <div>
                  <p className="text-sm text-red-800 font-medium">Campaign End</p>
                  <p className="text-xs text-red-600 mt-1">
                    This node marks the end of your email campaign flow. No further actions will be taken after this
                    point.
                  </p>
                </div>
              </div>
            </div>
          </div>
        )

      default:
        return (
          <div className="text-center text-gray-500 py-8">
            <p>No properties available for this node type.</p>
          </div>
        )
    }
  }

  return (
    <div className="w-80 bg-white border-l border-gray-200 flex flex-col">
      <div className="p-4 border-b border-gray-100 flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-gray-900">Properties</h3>
          <p className="text-sm text-gray-500 mt-1">{selectedNodeData.data.label}</p>
        </div>
        <button onClick={handleClose} className="p-1 hover:bg-gray-100 rounded">
          <X className="w-4 h-4 text-gray-500" />
        </button>
      </div>

      <div className="flex-1 p-4 overflow-y-auto">{renderNodeProperties()}</div>
    </div>
  )
}
