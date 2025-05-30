'use client'

import React from 'react'
import { LoginContextProvider, useLoginContext } from "@/providers/LoginContext";
import { StateContextProvider, useStateContext } from "@/providers/StateContext";

export const Providers = ({ children }) => {
    return (
        <LoginContextProvider>
            <StateContextProvider>{children}</StateContextProvider>
        </LoginContextProvider>
    )
}

export { useLoginContext, useStateContext };
