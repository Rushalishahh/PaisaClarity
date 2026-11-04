import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'

function Login() {
  const navigate = useNavigate()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError("")
    setLoading(true)

    try {
      // api() raises with the backend's message on failure (e.g. wrong
      // credentials -> 400 "Incorrect email or password").
      const data = await api("/auth/login", { method: "POST", body: { email, password } })

      localStorage.setItem("token", data.access_token)
      navigate("/dashboard")
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-navy flex items-center justify-center px-4">
      <div className="w-full max-w-md bg-navy-light rounded-3xl p-8 shadow-2xl">
        <h1 className="text-3xl font-bold text-white mb-1">Welcome back</h1>
        <p className="text-gray-400 mb-8">Log in to your finance dashboard</p>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="block text-sm text-gray-300 mb-1.5">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full bg-navy border border-gray-700 rounded-xl px-4 py-3 text-white placeholder-gray-500 focus:outline-none focus:border-mint transition-colors"
              placeholder="you@example.com"
            />
          </div>

          <div>
            <label className="block text-sm text-gray-300 mb-1.5">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full bg-navy border border-gray-700 rounded-xl px-4 py-3 text-white placeholder-gray-500 focus:outline-none focus:border-mint transition-colors"
              placeholder="••••••••"
            />
          </div>

          {error && (
            <p className="text-coral text-sm bg-coral/10 border border-coral/30 rounded-lg px-4 py-2">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-mint hover:bg-mint-dark text-navy font-semibold rounded-xl py-3 transition-colors disabled:opacity-60"
          >
            {loading ? "Logging in..." : "Log In"}
          </button>
        </form>

        <p className="text-gray-400 text-sm text-center mt-6">
          Don't have an account?{" "}
          <Link to="/signup" className="text-mint hover:underline">
            Sign up
          </Link>
        </p>
      </div>
    </div>
  )
}

export default Login