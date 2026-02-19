import React from 'react';
import { motion } from 'framer-motion';
import { Save } from 'lucide-react';

const Settings: React.FC = () => {
    return (
        <motion.div
            className="p-8 max-w-4xl mx-auto"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.3 }}
        >
            <header className="mb-8">
                <h1 className="text-3xl font-bold text-slate-800 mb-2">Settings</h1>
                <p className="text-slate-500">Manage your application preferences and configurations.</p>
            </header>

            <div className="space-y-6">
                {/* Profile Section */}
                <section className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
                    <h2 className="text-xl font-semibold text-slate-800 mb-4">Profile Settings</h2>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div className="space-y-2">
                            <label className="text-sm font-medium text-slate-700">Full Name</label>
                            <input
                                type="text"
                                className="w-full px-4 py-2 rounded-lg border border-slate-300 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all"
                                placeholder="John Doe"
                                disabled
                            />
                        </div>
                        <div className="space-y-2">
                            <label className="text-sm font-medium text-slate-700">Email Address</label>
                            <input
                                type="email"
                                className="w-full px-4 py-2 rounded-lg border border-slate-300 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all"
                                placeholder="john@example.com"
                                disabled
                            />
                        </div>
                    </div>
                </section>

                {/* API & RAG Settings */}
                <section className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
                    <h2 className="text-xl font-semibold text-slate-800 mb-4">RAG Engine Configuration</h2>
                    <div className="space-y-4">
                        <div className="flex items-center justify-between p-4 bg-slate-50 rounded-lg border border-slate-100">
                            <div>
                                <h3 className="font-medium text-slate-900">LLM Model</h3>
                                <p className="text-sm text-slate-500">Select the model used for text generation</p>
                            </div>
                            <select className="px-3 py-2 rounded-lg border border-slate-300 bg-white text-sm focus:ring-2 focus:ring-blue-500 outline-none">
                                <option>Llama 3 (8b)</option>
                                <option>Mistral 7b</option>
                                <option>GPT-4o (Remote)</option>
                            </select>
                        </div>

                        <div className="flex items-center justify-between p-4 bg-slate-50 rounded-lg border border-slate-100">
                            <div>
                                <h3 className="font-medium text-slate-900">Retrieval Strategy</h3>
                                <p className="text-sm text-slate-500">Configure how context is retrieved</p>
                            </div>
                            <select className="px-3 py-2 rounded-lg border border-slate-300 bg-white text-sm focus:ring-2 focus:ring-blue-500 outline-none">
                                <option>Hybrid (Dense + Sparse)</option>
                                <option>Dense Only</option>
                                <option>Sparse Only</option>
                            </select>
                        </div>
                    </div>
                </section>

                <div className="flex justify-end pt-4">
                    <button className="flex items-center gap-2 px-6 py-2.5 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors shadow-sm hover:shadow-md">
                        <Save size={18} />
                        Save Changes
                    </button>
                </div>
            </div>
        </motion.div>
    );
};

export default Settings;
