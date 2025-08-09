import { useState, useEffect } from 'react';
import { Loader2, AlertCircle } from 'lucide-react';
import type { FiscalNote, Bill } from '../types';
import { getBills, getBillFiscalNote } from '../services/api';

const BillFiscalNote = () => {
  const [bills, setBills] = useState<Bill[]>([]);
  const [selectedBill, setSelectedBill] = useState<string>('');
  const [fiscalNote, setFiscalNote] = useState<FiscalNote | null>(null);
  const [loadingBills, setLoadingBills] = useState(true);
  const [loadingNote, setLoadingNote] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchBills = async () => {
      setLoadingBills(true);
      setError(null);
      try {
        const fetchedBills = await getBills(); 
        setBills(fetchedBills);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load bills');
      } finally {
        setLoadingBills(false);
      }
    };
    fetchBills();
  }, []);

  useEffect(() => {
    if (!selectedBill) {
      setFiscalNote(null);
      return;
    }

    const fetchFiscalNote = async () => {
      setLoadingNote(true);
      setError(null);
      setFiscalNote(null);
      try {
        const note = await getBillFiscalNote(selectedBill);
        setFiscalNote(note);
      } catch (err) {
        setError(err instanceof Error ? err.message : `Failed to load fiscal note for ${selectedBill}`);
        setFiscalNote(null);
      } finally {
        setLoadingNote(false);
      }
    };

    fetchFiscalNote();
  }, [selectedBill]);

  return (
    <div className="p-6 bg-gray-50 h-full overflow-y-auto">
      <div className="max-w-4xl mx-auto">
        <div className="mb-6">
          <label htmlFor="bill-select" className="block text-sm font-medium text-gray-700 mb-1">
            Select a Bill
          </label>
          {loadingBills ? (
            <div className="flex items-center space-x-2 text-gray-500">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Loading bills...</span>
            </div>
          ) : (
            <select
              id="bill-select"
              value={selectedBill}
              onChange={(e) => setSelectedBill(e.target.value)}
              className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm rounded-md"
              disabled={loadingBills || loadingNote}
            >
              <option value="">-- Select a Bill --</option>
              {bills.map(bill => (
                <option key={bill.id} value={bill.id}>{bill.name}</option>
              ))}
            </select>
          )}
        </div>

        {loadingNote && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-8 h-8 text-blue-600 animate-spin" />
             <p className="ml-2">Generating fiscal note...</p>
          </div>
        )}

        {error && (
            <div className="my-4 flex items-center space-x-2 text-red-600 p-4 bg-red-100 rounded-md">
                <AlertCircle className="w-5 h-5" />
                <span>{error}</span>
            </div>
        )}

        {fiscalNote && !loadingNote && (
          <div className="bg-white p-6 rounded-lg shadow-md animate-fade-in">
             <h2 className="text-2xl font-bold text-gray-800 mb-4 capitalize">Fiscal Note for {selectedBill}</h2>
            {Object.entries(fiscalNote).map(([key, value]) => (
              <div key={key} className="mb-6">
                <h3 className="text-lg font-semibold text-gray-800 capitalize border-b pb-2 mb-2">{key.replace(/_/g, ' ')}</h3>
                <p className="text-gray-700 whitespace-pre-wrap">{String(value)}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default BillFiscalNote; 