import { Link } from 'react-router-dom'
import { Wordmark } from '../components/AppShell'

function NavBar() {
  return (
    <nav className="flex items-center justify-between px-6 sm:px-10 py-6 max-w-6xl mx-auto">
      <Wordmark />
      <div className="flex items-center gap-3">
        <Link to="/login" className="text-gray-300 hover:text-white text-sm px-4 py-2 transition-colors">
          Log in
        </Link>
        <Link
          to="/signup"
          className="bg-mint hover:bg-mint-dark text-navy font-semibold rounded-xl px-4 py-2 text-sm transition-colors"
        >
          Create account
        </Link>
      </div>
    </nav>
  )
}

function TransformDemo() {
  return (
    <div className="bg-navy-light rounded-2xl p-6 shadow-xl w-full max-w-sm">
      <p className="text-gray-500 text-xs mb-3 font-mono">From your statement</p>
      <div className="bg-navy rounded-xl px-4 py-3 font-mono text-sm text-gray-400 mb-4">
        UPI-ZOMATO-785386&nbsp;&nbsp;&nbsp;-₹420.00
      </div>
      <div className="flex justify-center mb-4">
        <div className="w-px h-6 bg-gray-700" />
      </div>
      <p className="text-gray-500 text-xs mb-3 font-mono">What you see</p>
      <div className="bg-navy rounded-xl px-4 py-3 flex items-center justify-between">
        <span className="text-white font-medium">Zomato</span>
        <span className="text-coral font-semibold">₹420</span>
      </div>
      <div className="mt-2 inline-block bg-mint/10 text-mint text-xs rounded-full px-3 py-1">
        Food
      </div>
    </div>
  )
}

function Landing() {
  return (
    <div className="min-h-screen bg-navy">
      <NavBar />

      {/* Hero */}
      <section className="max-w-6xl mx-auto px-6 sm:px-10 pt-12 pb-24 grid md:grid-cols-2 gap-12 items-center">
        <div>
          <h1 className="text-4xl sm:text-5xl font-bold text-white leading-tight">
            Your bank statement, actually readable.
          </h1>
          <p className="text-gray-400 text-lg mt-6 leading-relaxed max-w-md">
            Upload a CSV or PDF from your bank and see exactly where your money goes,
            what charges you every month without you noticing, and what your
            investments are worth today.
          </p>
          <div className="flex items-center gap-4 mt-8">
            <Link
              to="/signup"
              className="bg-mint hover:bg-mint-dark text-navy font-semibold rounded-xl px-6 py-3 transition-colors"
            >
              Create your account
            </Link>
            <Link to="/login" className="text-gray-300 hover:text-white text-sm">
              I already have an account
            </Link>
          </div>
        </div>

        <div className="flex justify-center md:justify-end">
          <TransformDemo />
        </div>
      </section>

      {/* Feature 1: Spending insights - text left, visual right */}
      <section className="max-w-6xl mx-auto px-6 sm:px-10 py-16 grid md:grid-cols-2 gap-12 items-center border-t border-gray-800">
        <div>
          <h2 className="text-2xl sm:text-3xl font-semibold text-white">
            See where your money actually goes
          </h2>
          <p className="text-gray-400 mt-4 leading-relaxed max-w-md">
            Every transaction gets sorted into a category automatically —
            food, shopping, bills, groceries. You get monthly totals, a
            forecast for next month, and a flag whenever a category spikes
            well above its usual average.
          </p>
        </div>
        <div className="bg-navy-light rounded-2xl p-6 shadow-lg">
          <div className="space-y-3">
            {[
              { label: "Food", value: 68, color: "bg-mint" },
              { label: "Shopping", value: 45, color: "bg-coral" },
              { label: "Bills", value: 30, color: "bg-mint-dark" },
              { label: "Groceries", value: 22, color: "bg-coral-dark" },
            ].map((row) => (
              <div key={row.label} className="flex items-center gap-3">
                <span className="text-gray-400 text-sm w-20">{row.label}</span>
                <div className="flex-1 h-2.5 bg-navy rounded-full overflow-hidden">
                  <div className={`h-full ${row.color} rounded-full`} style={{ width: `${row.value}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Feature 2: Investments - visual left, text right */}
      <section className="max-w-6xl mx-auto px-6 sm:px-10 py-16 grid md:grid-cols-2 gap-12 items-center border-t border-gray-800">
        <div className="order-2 md:order-1 bg-navy-light rounded-2xl p-6 shadow-lg">
          <div className="flex justify-between items-center mb-4 pb-4 border-b border-gray-800">
            <span className="text-gray-400 text-sm">Net worth</span>
            <span className="text-white text-2xl font-bold">₹2,14,600</span>
          </div>
          <div className="flex justify-between items-center bg-navy rounded-xl px-4 py-3 mb-2">
            <span className="text-gray-200">HDFC Top 100 Fund</span>
            <span className="text-mint">+12.4%</span>
          </div>
          <div className="flex justify-between items-center bg-navy rounded-xl px-4 py-3">
            <span className="text-gray-200">LIC Jeevan Anand</span>
            <span className="text-gray-400 text-sm">Due in 14 days</span>
          </div>
        </div>
        <div className="order-1 md:order-2">
          <h2 className="text-2xl sm:text-3xl font-semibold text-white">
            Investments and policies, one place
          </h2>
          <p className="text-gray-400 mt-4 leading-relaxed max-w-md">
            Track mutual funds with live NAV pricing pulled straight from the
            market, alongside insurance policies and recurring SIPs — with a
            reminder before every premium comes due, so nothing lapses
            because you forgot.
          </p>
        </div>
      </section>

      {/* Credible detail section */}
      <section className="max-w-6xl mx-auto px-6 sm:px-10 py-16 border-t border-gray-800">
        <h2 className="text-2xl sm:text-3xl font-semibold text-white max-w-lg">
          Built around how Indian bank statements actually look
        </h2>
        <p className="text-gray-400 mt-4 leading-relaxed max-w-lg">
          Txn Date, Value Date, Withdrawal Amt., Deposit Amt., Closing
          Balance — the format your bank already exports. No reformatting,
          no manual cleanup. Upload your statement as a CSV or PDF and you're done.
        </p>
      </section>

      {/* Final CTA */}
      <section className="max-w-6xl mx-auto px-6 sm:px-10 py-20 border-t border-gray-800 text-center">
        <h2 className="text-3xl font-semibold text-white">Ready to see your money clearly?</h2>
        <Link
          to="/signup"
          className="inline-block mt-6 bg-mint hover:bg-mint-dark text-navy font-semibold rounded-xl px-8 py-3 transition-colors"
        >
          Create your account
        </Link>
      </section>

      <footer className="max-w-6xl mx-auto px-6 sm:px-10 py-8 text-gray-600 text-sm border-t border-gray-800">
        Paisa Clarity
      </footer>
    </div>
  )
}

export default Landing