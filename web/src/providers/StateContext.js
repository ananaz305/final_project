import React, { createContext, useState, useContext } from 'react';

const StateContext = createContext(null);

export const useStateContext = () => {
    const context = useContext(StateContext)

    if (!context) {
        throw new Error('useContext must be used within a StateContextProvider')
    }
    return context
}

export const StateContextProvider = ({ children }) => {
    const [appointmentList, setAppointmentList] = useState([]);

    return <StateContext.Provider value={{ appointmentList, setAppointmentList }}>{children}</StateContext.Provider>
}
