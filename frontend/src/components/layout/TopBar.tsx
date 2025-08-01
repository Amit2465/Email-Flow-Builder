"use client"

import type React from "react"
import { Play, RotateCcw, AlertTriangle, X } from "lucide-react"
import { useFlowStore } from "../../store/flowStore"
import { useState, useEffect } from "react"

export const TopBar: React.FC = () => {
  const { isValidFlow, validationErrors, exportFlow, resetFlow, contactFile } = useFlowStore()
  const [showErrorToast, setShowErrorToast] = useState(false)
  const [toastErrors, setToastErrors] = useState<string[]>([])

  const parseCSVData = (csvText: string) => {
    const lines = csvText.split("\n").filter((line) => line.trim() !== "")
    if (lines.length === 0) return { name: [], email: [] }

    // Get headers and convert to lowercase for comparison
    const headers = lines[0].split(",").map((h) => h.trim().replace(/"/g, "").toLowerCase())

    console.log("CSV Headers found:", headers)

    // Find name and email column indices - simplified to only look for "name" and "email"
    const nameIndex = headers.findIndex((h) => h === "name")
    const emailIndex = headers.findIndex((h) => h === "email" || h.includes("email") || h.includes("mail"))

    console.log(`Name column index: ${nameIndex} (${nameIndex >= 0 ? headers[nameIndex] : "not found"})`)
    console.log(`Email column index: ${emailIndex} (${emailIndex >= 0 ? headers[emailIndex] : "not found"})`)

    const names: string[] = []
    const emails: string[] = []

    // Process data rows (skip header row)
    for (let i = 1; i < lines.length; i++) {
      const values = lines[i].split(",").map((v) => v.trim().replace(/"/g, ""))

      // Handle name column
      if (nameIndex >= 0 && values[nameIndex] && values[nameIndex].trim() !== "") {
        names.push(values[nameIndex].trim())
      } else {
        names.push(`Contact ${i}`) // Default name if not found or empty
      }

      // Handle email column
      if (emailIndex >= 0 && values[emailIndex] && values[emailIndex].trim() !== "") {
        emails.push(values[emailIndex].trim())
      } else {
        emails.push("") // Empty email if not found
      }
    }

    console.log(`Processed ${names.length} contacts from CSV`)
    return { name: names, email: emails }
  }

  const convertFlowToJSON = () => {
    const flowData = exportFlow()

    const flowJSON = {
      campaign: {
        id: `campaign_${Date.now()}`,
        name: "Email Campaign Flow",
        created_at: new Date().toISOString(),
        status: "ready",
      },
      nodes: flowData.nodes.map((node) => ({
        id: node.id,
        type: node.type,
        position: node.position,
        configuration: {
          label: node.data.label,
          ...node.data.config,
        },
      })),
      connections: flowData.edges.map((edge) => ({
        id: edge.id,
        from_node: edge.source,
        to_node: edge.target,
        connection_type: edge.sourceHandle || "default",
        animated: edge.animated || false,
      })),
      workflow: {
        start_node: "start-1",
        total_nodes: flowData.nodes.length,
        total_connections: flowData.edges.length,
      },
      contact_file: flowData.contactFile
        ? {
            filename: flowData.contactFile.name,
            size: flowData.contactFile.size,
            type: flowData.contactFile.type,
            uploaded_at: new Date(flowData.contactFile.lastModified).toISOString(),
          }
        : null,
    }

    return flowJSON
  }

  const handleRunFlow = async () => {
    if (!contactFile) {
      setToastErrors(["Please upload a contact file before running the campaign!"])
      setShowErrorToast(true)
      return
    }

    if (!isValidFlow) {
      setToastErrors(validationErrors)
      setShowErrorToast(true)
      return
    }

    try {
      // Read and parse CSV file
      const fileText = await contactFile.text()
      const contactData = parseCSVData(fileText)

      // Convert flow to JSON
      const flowJSON = convertFlowToJSON()

      // Print to console with clear separators
      console.log("=".repeat(50))
      console.log("=== CONTACT DATA (JSON) ===")
      console.log("=".repeat(50))
      console.log(JSON.stringify(contactData, null, 2))

      console.log("\n" + "=".repeat(50))
      console.log("=== EMAIL CAMPAIGN FLOW (JSON) ===")
      console.log("=".repeat(50))
      console.log(JSON.stringify(flowJSON, null, 2))
      console.log("=".repeat(50))

      // Show success message
      alert(
        `Campaign flow started successfully!\n\nContacts loaded: ${contactData.name.length}\nValid emails: ${contactData.email.filter((e) => e !== "").length}\nFlow nodes: ${flowJSON.nodes.length}\n\nCheck console for detailed JSON data.`,
      )
    } catch (error) {
      console.error("Error processing files:", error)
      setToastErrors(["Error reading contact file. Please ensure it's a valid CSV file."])
      setShowErrorToast(true)
    }
  }

  const handleResetFlow = () => {
    if (confirm("Are you sure you want to reset the entire flow? This will also remove the uploaded contact file.")) {
      resetFlow()
    }
  }

  // Auto-hide toast after 5 seconds
  useEffect(() => {
    if (showErrorToast) {
      const timer = setTimeout(() => {
        setShowErrorToast(false)
      }, 5000)
      return () => clearTimeout(timer)
    }
  }, [showErrorToast])

  return (
    <>
      <div className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <h1 className="text-xl font-semibold text-gray-900">Email Campaign Builder</h1>
        </div>

        <div className="flex items-center space-x-3">
          <button
            onClick={handleResetFlow}
            className="flex items-center space-x-2 px-4 py-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg font-medium transition-all"
          >
            <RotateCcw className="w-4 h-4" />
            <span>Reset</span>
          </button>

          <button
            onClick={handleRunFlow}
            className="flex items-center space-x-2 px-4 py-2 rounded-lg font-medium transition-all bg-blue-600 text-white hover:bg-blue-700 shadow-sm hover:shadow-md"
          >
            <Play className="w-4 h-4" />
            <span>Run Flow</span>
          </button>
        </div>
      </div>

      {/* Error Toast */}
      {showErrorToast && (
        <div className="fixed top-20 right-6 z-50 max-w-md">
          <div className="bg-red-50 border border-red-200 rounded-lg shadow-lg p-4">
            <div className="flex items-start justify-between">
              <div className="flex items-start space-x-3">
                <AlertTriangle className="w-5 h-5 text-red-600 mt-0.5 flex-shrink-0" />
                <div>
                  <h3 className="text-sm font-medium text-red-800">Cannot Run Campaign</h3>
                  <div className="mt-2 text-sm text-red-700">
                    <ul className="list-disc list-inside space-y-1">
                      {toastErrors.map((error, index) => (
                        <li key={index}>{error}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
              <button
                onClick={() => setShowErrorToast(false)}
                className="flex-shrink-0 ml-4 p-1 hover:bg-red-100 rounded"
              >
                <X className="w-4 h-4 text-red-600" />
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
