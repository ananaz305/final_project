import React, { createContext, useState, useContext } from 'react';

const LoginContext = createContext(null);

export const useLoginContext = () => {
    const context = useContext(LoginContext)

    if (!context) {
        throw new Error('useContext must be used within a LoginContextProvider')
    }
    return context
}

export const LoginContextProvider = ({ children }) => {
    const [user, setUser] = useState(null);

    return <LoginContext.Provider value={{ user, setUser }}>{children}</LoginContext.Provider>
}
