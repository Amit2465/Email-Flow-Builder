"use client"

import { useState } from "react"

export const ConnectionTest = () => {
  const [status, setStatus] = useState<string>("")
  const [loading, setLoading] = useState(false)

  const testBackendConnection = async () => {
    setLoading(true)
    try {
      const response = await fetch("http://localhost:8000/test-connection")
      if (response.ok) {
        const data = await response.json()
        setStatus(`✅ Backend connected: ${data.message}`)
      } else {
        setStatus("❌ Backend connection failed")
      }
    } catch (error) {
      setStatus("❌ Backend connection error")
    }
    setLoading(false)
  }

  return (
    <div className="p-4 border rounded-lg bg-gray-50">
      <h3 className="font-semibold mb-2">Backend Connection Test</h3>
      <button
        onClick={testBackendConnection}
        disabled={loading}
        className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50"
      >
        {loading ? "Testing..." : "Test Connection"}
      </button>
      {status && (
        <p className="mt-2 text-sm">{status}</p>
      )}
    </div>
  )
} 