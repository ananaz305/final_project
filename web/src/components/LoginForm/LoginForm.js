import React, { useState } from 'react';

import Button from '@mui/material/Button';
import Input from '@mui/material/TextField';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import Chip from '@mui/material/Chip';
import Tabs from '@mui/material/Tabs';
import Tab from '@mui/material/Tab';
import {useLoginContext} from "@/providers";

export const LoginForm = ({ isOpen, onClose }) => {
    const { setUser } = useLoginContext();

    const [value, setValue] = useState(0);

    const handleChange = (event, newValue) => {
        setValue(newValue);
    };

    return (
        <Dialog
            open={isOpen}
            onClose={onClose}
            slotProps={{
                paper: {
                    component: 'form',
                    onSubmit: (event) => {
                        event.preventDefault();
                        const formData = new FormData(event.currentTarget);
                        const formJson = Object.fromEntries(formData.entries());

                        setUser(formJson);

                        onClose();
                    },
                },
            }}
        >
            <DialogTitle>GOV.UK Unity</DialogTitle>
            <DialogContent>
                <DialogContentText>
                    Access government services in one place
                </DialogContentText>
                <Tabs value={value} onChange={handleChange}>
                    <Tab label="Login" />
                    <Tab label="Register" />
                </Tabs>
                <Chip label="Demo version" color="info" sx={{ marginTop: '6px' }} />
                {value === 1 && (
                    <>
                        <Input
                            margin="dense"
                            id="firstName"
                            name="firstName"
                            label="First Name"
                            type="text"
                            fullWidth
                            variant="standard"
                            required
                        />
                        <Input
                            margin="dense"
                            id="lastName"
                            name="lastName"
                            label="Last Name"
                            type="text"
                            fullWidth
                            variant="standard"
                            required
                        />
                    </>
                )}
                <Input
                    required
                    margin="dense"
                    id="email"
                    name="email"
                    label="Email"
                    type="email"
                    fullWidth
                    variant="standard"
                />
                <Input
                    required
                    margin="dense"
                    id="password"
                    name="password"
                    label="Password"
                    type="password"
                    fullWidth
                    variant="standard"
                />
            </DialogContent>
            <DialogActions>
                <Button type="submit">
                    Submit
                </Button>
            </DialogActions>
        </Dialog>
    );
}
